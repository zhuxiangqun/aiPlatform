"""
Subagent Coordinator

Coordinates task execution across multiple Subagents.

Design: Each Subagent is a lightweight conversational agent with restricted
tool permissions. The coordinator dispatches tasks and collects summarized
results per §5.26 Subagent 摘要原则.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .config import SubagentConfig, SubagentInstance
from .registry import get_subagent_registry

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """Execution strategy for multiple Subagents"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    COORDINATED = "coordinated"


@dataclass
class SubagentResult:
    """Result from a Subagent execution"""
    subagent_name: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    tool_calls: List[Dict] = field(default_factory=list)
    tokens_used: int = 0
    duration_ms: int = 0


class SubagentCoordinator:
    """Coordinates execution of Subagents via conversational AI agents.

    Each Subagent runs as a lightweight conversational agent with restricted
    tool permissions. The coordinator creates agents, dispatches tasks, and
    collects summarized results for the parent agent.
    """

    def __init__(self, create_agent_fn=None, get_tool_registry_fn=None):
        self._registry = None
        self._active_instances: Dict[str, SubagentInstance] = {}
        self._create_agent_fn = create_agent_fn
        self._get_tool_registry_fn = get_tool_registry_fn
    
    async def _get_registry(self):
        if self._registry is None:
            self._registry = get_subagent_registry()
            await self._registry.initialize()
        return self._registry
    
    async def create_instance(
        self,
        name: str,
        session_id: str,
        custom_config: Optional[SubagentConfig] = None
    ) -> SubagentInstance:
        """Create a new Subagent instance"""
        registry = await self._get_registry()
        
        if custom_config:
            config = custom_config
        else:
            config = registry.get(name)
            if not config:
                raise ValueError(f"Subagent '{name}' not found in registry")
        
        instance = SubagentInstance(
            config=config,
            session_id=session_id,
            state="created",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        self._active_instances[f"{session_id}:{name}"] = instance
        return instance
    
    async def execute_single(
        self,
        task: str,
        subagent_name: str,
        context: Optional[List[Dict]] = None,
        *,
        isolate_context: bool = True,  # P1-2: 隔离上下文, 仅返回摘要
        read_only_context: bool = False,  # P1-2: 只读父 context 摘要 (≤500 tokens)
    ) -> SubagentResult:
        """Execute a single Subagent via a conversational AI agent.

        Creates a lightweight conversational agent from the subagent config,
        binds allowed tools, executes the task, and returns a summarized
        result (max ~800 chars per §5.26 Subagent 摘要原则).
        """
        start_time = datetime.now(timezone.utc)
        try:
            instance = await self.create_instance(
                name=subagent_name,
                session_id=f"task-{datetime.now(timezone.utc).timestamp()}"
            )
            instance.state = "running"
            instance.started_at = datetime.now(timezone.utc).isoformat()

            # Build conversation context from system prompt + task
            messages: List[Dict[str, str]] = []
            if instance.config.system_prompt:
                messages.append({"role": "system", "content": instance.config.system_prompt})
            if context:
                if isolate_context:
                    # P1-2: Isolated mode — only pass a brief summary, not full history
                    summary_parts = []
                    for msg in context[-3:]:  # Last 3 messages only
                        content = str(msg.get("content", ""))[:200]
                        if content:
                            summary_parts.append(content)
                    if summary_parts:
                        messages.append({"role": "system", "content": "[上下文摘要] " + " | ".join(summary_parts)})
                elif read_only_context:
                    # Read-only mode: pass a compact summary (≤500 tokens)
                    context_text = " ".join(str(m.get("content", ""))[:150] for m in context[-5:])
                    messages.append({"role": "system", "content": f"[只读上下文] {context_text[:500]}"})
                else:
                    for msg in context:
                        messages.append({
                            "role": msg.get("role", "user"),
                            "content": str(msg.get("content", "")),
                        })
            messages.append({"role": "user", "content": task})

            # Create agent via injected factory (DI) or fallback to import
            if self._create_agent_fn:
                create_agent = self._create_agent_fn
                get_tool_registry = self._get_tool_registry_fn
            else:
                from core.api.core_facade import create_agent, get_tool_registry
            agent = create_agent(
                agent_type="conversational",
                config={
                    "name": f"subagent-{subagent_name}",
                    "timeout": instance.config.timeout,
                    "max_tokens": instance.config.max_context_tokens,
                },
                system_prompt=instance.config.system_prompt,
            )

            available_tools = instance.config.allowed_tools[:]
            tool_registry = get_tool_registry()
            for tool_name in available_tools:
                if instance.config.can_use_tool(tool_name):
                    tool = tool_registry.get(tool_name) if hasattr(tool_registry, "get") else None
                    if tool and hasattr(agent, "add_tool"):
                        agent.add_tool(tool)

            # Execute and collect output
            import uuid as _uuid
            from core.harness.interfaces.agent import AgentContext
            agent_ctx = AgentContext(
                session_id=f"subagent-{subagent_name}",
                user_id="subagent_coordinator",
                messages=messages,
                variables={"_run_id": f"run_{_uuid.uuid4().hex[:16]}"},
            )

            # ── Propagate parent's workspace context (toolset + mcp_ids) to child agent ──
            sub_ws_token = None
            try:
                from core.harness.kernel.execution_context import (
                    get_active_workspace_context,
                    set_active_workspace_context,
                    reset_active_workspace_context,
                    ActiveWorkspaceContext,
                )
                parent_ws = get_active_workspace_context()
                if parent_ws:
                    sub_ws_token = set_active_workspace_context(
                        ActiveWorkspaceContext(
                            toolset=getattr(parent_ws, "toolset", None),
                            mcp_ids=list(getattr(parent_ws, "mcp_ids", []) or []) or None,
                            repo_root=getattr(parent_ws, "repo_root", None),
                        )
                    )
            except Exception:
                sub_ws_token = None

            # ── Also propagate request context (user_id, session_id) to sub-agent ──
            req_token = None
            try:
                from core.harness.kernel.execution_context import (
                    get_active_request_context,
                    set_active_request_context,
                    reset_active_request_context,
                    ActiveRequestContext,
                )
                parent_req = get_active_request_context()
                if parent_req:
                    req_token = set_active_request_context(
                        ActiveRequestContext(
                            user_id=getattr(parent_req, "user_id", "subagent_coordinator"),
                            session_id=getattr(parent_req, "session_id", f"subagent-{subagent_name}"),
                            entrypoint="subagent",
                        )
                    )
            except Exception:
                req_token = None

            try:
                result = await agent.execute(agent_ctx)
            finally:
                if req_token is not None:
                    try:
                        from core.harness.kernel.execution_context import reset_active_request_context
                        reset_active_request_context(req_token)
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
                if sub_ws_token is not None:
                    try:
                        from core.harness.kernel.execution_context import reset_active_workspace_context
                        reset_active_workspace_context(sub_ws_token)
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)

            if result.success:
                output = result.output or ""
                if isinstance(output, dict):
                    output = output.get("content", str(output))
                # Summarize per §5.26: parent needs concise summary, not full output
                summarized = await self._summarize_output(str(output), max_chars=800)
                duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                instance.state = "completed"
                instance.completed_at = datetime.now(timezone.utc).isoformat()
                return SubagentResult(
                    subagent_name=subagent_name,
                    success=True,
                    output=summarized,
                    tokens_used=getattr(result, "tokens_used", 0) or 0,
                    duration_ms=duration,
                )
            else:
                duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                instance.state = "error"
                return SubagentResult(
                    subagent_name=subagent_name,
                    success=False,
                    error=str(getattr(result, "error", "Agent execution failed")),
                    duration_ms=duration,
                )
        except Exception as e:
            logger.error(f"Subagent '{subagent_name}' failed: {e}")
            duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            return SubagentResult(
                subagent_name=subagent_name,
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    @staticmethod
    def _filter_protocol_violations(output: str) -> str:
        """确定性移除协议禁止的内容（CLAODE.md §5.26 强制执行）。

        在摘要流程最前面运行——不依赖 LLM 判断，100% 确定性。
        """
        import re

        # 1. 代码块: ```...``` → [code removed]
        output = re.sub(r'```[\s\S]*?```', '[code removed]', output)

        # 2. 工具调用链: "Action:" / "sys_tool_call" / "调用工具" 行
        output = re.sub(
            r'(?:^(?:Action|Tool call|调用工具|sys_tool_call|sys_skill_call)[:\s]+.*(?:\n|$))+',
            '[tool calls removed]\n', output, flags=re.MULTILINE | re.IGNORECASE)

        # 3. 推理标记: "Thought:" / "Let me think" / "思考：" / "推理："
        output = re.sub(
            r'^(?:Thought|Let me think|思考|推理|Reasoning)[:\s]+.*(?:\n|$)',
            '', output, flags=re.MULTILINE | re.IGNORECASE)

        return output.strip()


    @staticmethod
    async def _summarize_output(output: str, max_chars: int = 800) -> str:
        """v2.0: 智能摘要 — 4 层降级策略，全部确定性。

        第 0 层: 正则过滤协议禁止内容（100% 确定性）
        第 1 层: 5 级上下文压缩（保留关键语义信息）
        第 2 层: LLM 轻量格式化摘要（输入已清理，LLM 只需提取结论）
        第 3 层: 安全截断（在句号/换行边界断开）
        """
        # ── 第 0 层: 协议强制过滤 ──
        output = SubagentCoordinator._filter_protocol_violations(output)

        if len(output) <= max_chars:
            return output
            return output

        # ── 第 1 层: 上下文压缩 ──
        try:
            from core.harness.memory.manager import MemoryManager
            mgr = MemoryManager()
            if hasattr(mgr, '_compression') and mgr._compression is not None:
                compressed = await mgr._compression.compress_lightweight(
                    output, target_chars=max_chars)
                if compressed and len(compressed) > 0 and len(compressed) < len(output) * 0.8:
                    return compressed[:max_chars]
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # ── 第 2 层: LLM 轻量摘要 ──
        try:
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.model_injection import best_model_for_purpose
            prompt = (
                f"Summarize the following output within {max_chars} characters. "
                "Keep key findings, numbers, decisions, and conclusions. "
                "Drop tool call chains, intermediate reasoning steps, and code blocks. "
                "Return only the summary, no preamble:\n\n"
                f"{output[:4000]}"
            )
            resp = await sys_llm_generate(
                best_model_for_purpose("chat"),
                [{"role": "user", "content": prompt}],
                max_tokens=200, temperature=0.0,
                trace_context={"source": "subagent_summarize"},
            )
            content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
            if content and len(content) > 10:
                return content[:max_chars]
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # ── 第 3 层: 安全截断 ──
        return SubagentCoordinator._safe_truncate(output, max_chars)


    @staticmethod
    def _safe_truncate(text: str, max_chars: int) -> str:
        """在最近句号/换行边界断开，不破坏句子完整性。"""
        if len(text) <= max_chars:
            return text
        cut = text[:max_chars]
        for sep in ['\n\n', '。', '. ', '\n', '，', ', ']:
            idx = cut.rfind(sep)
            if idx > max_chars * 0.6:
                return cut[:idx + len(sep)] + f"\n\n... [从 {len(text)} 字符摘要]"
        return cut + f"\n\n... [从 {len(text)} 字符摘要]"
    
    async def execute_parallel(
        self,
        task: str,
        subagent_names: List[str],
        context: Optional[List[Dict]] = None
    ) -> List[SubagentResult]:
        """Execute multiple Subagents in parallel"""
        results = await asyncio.gather(
            *[self.execute_single(task, name, context) for name in subagent_names],
            return_exceptions=True
        )
        
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(SubagentResult(
                    subagent_name=subagent_names[i],
                    success=False,
                    error=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def execute_sequential(
        self,
        task: str,
        subagent_names: List[str],
        context: Optional[List[Dict]] = None
    ) -> List[SubagentResult]:
        """Execute multiple Subagents sequentially"""
        results = []
        current_context = context or []
        
        for name in subagent_names:
            result = await self.execute_single(task, name, current_context)
            results.append(result)
            
            # Add result to context for next Subagent
            if result.success and result.output:
                current_context.append({
                    "role": "assistant",
                    "content": f"[{name}] {result.output}"
                })
        
        return results
    
    async def execute_coordinated(
        self,
        task: str,
        subagent_names: List[str],
        context: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Execute with coordinator pattern - analyze task and dispatch"""
        # First, analyze task to determine dispatch strategy
        analysis = self._analyze_task(task)
        
        if analysis["requires_parallel"]:
            sub_results = await self.execute_parallel(task, subagent_names, context)
        else:
            sub_results = await self.execute_sequential(task, subagent_names, context)
        
        # Aggregate results
        return self.aggregate_results(sub_results)
    
    def _analyze_task(self, task: str) -> Dict[str, Any]:
        """Analyze task to determine execution strategy"""
        task_lower = task.lower()
        
        return {
            "requires_parallel": any(kw in task_lower for kw in [
                "review", "analyze", "check", "audit", "multiple"
            ]),
            "estimated_complexity": "high" if "complex" in task_lower else "medium",
            "requires_coordination": "coordinate" in task_lower or "orchestrate" in task_lower
        }
    
    def aggregate_results(self, results: List[SubagentResult]) -> Dict[str, Any]:
        """Aggregate results from multiple Subagents"""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        total_tokens = sum(r.tokens_used for r in results)
        total_duration = sum(r.duration_ms for r in results)
        
        aggregated_output = "\n\n".join([
            f"## {r.subagent_name}\n{r.output or r.error}"
            for r in results
        ])
        
        return {
            "success": len(failed) == 0,
            "total_subagents": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "output": aggregated_output,
            "results": results,
            "total_tokens": total_tokens,
            "total_duration_ms": total_duration
        }
    
    async def cancel_instance(self, session_id: str, name: str) -> bool:
        """Cancel a running Subagent instance"""
        key = f"{session_id}:{name}"
        if key in self._active_instances:
            self._active_instances[key].state = "cancelled"
            return True
        return False
    
    def get_active_instances(self) -> Dict[str, SubagentInstance]:
        """Get all active instances"""
        return self._active_instances.copy()


# Global coordinator instance
_coordinator: Optional[SubagentCoordinator] = None


def get_subagent_coordinator(create_agent_fn=None, get_tool_registry_fn=None) -> SubagentCoordinator:
    """Get global Subagent coordinator. Optional DI callables for agent creation."""
    global _coordinator
    if _coordinator is None:
        _coordinator = SubagentCoordinator(
            create_agent_fn=create_agent_fn,
            get_tool_registry_fn=get_tool_registry_fn,
        )
    return _coordinator


__all__ = [
    "ExecutionStrategy",
    "SubagentResult",
    "SubagentCoordinator",
    "get_subagent_coordinator"
]