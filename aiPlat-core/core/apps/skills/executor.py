"""
Skill Executor Module

Provides SkillExecutor for executing skills with context management,
timeout control, and execution tracking.
"""

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from .base import BaseSkill
from .registry import get_skill_registry, SkillRegistry
from ...harness.interfaces import SkillContext, SkillResult, SkillStreamEvent
from ...apps.tools.base import get_tool_registry
from ...harness.syscalls import sys_skill_call
from core.utils.ids import new_prefixed_id
from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url


@dataclass
class ExecutionRecord:
    execution_id: str
    skill_name: str
    status: str  # pending, running, success, failed, timeout
    input_params: Dict[str, Any]
    output: Any = None
    error: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0
    latency: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SkillExecutor:
    """
    Skill Executor

    Executes skills with timeout control, execution tracking,
    and context management.
    """

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        default_timeout: float = None,
        discovery=None
    ):
        self._registry = registry or get_skill_registry()
        self._default_timeout = default_timeout or float(os.getenv("AIPLAT_SKILL_DEFAULT_TIMEOUT", "60"))
        self._executions: Dict[str, ExecutionRecord] = {}
        self._discovery = discovery

    async def execute(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None,
        mode: str = "inline"
    ) -> SkillResult:
        """Execute a skill by name
        
        Args:
            skill_name: Name of the skill to execute
            params: Parameters for the skill
            context: Execution context
            timeout: Execution timeout in seconds
            mode: Execution mode - "inline" or "fork"
        """
        if mode == "fork":
            return await self._execute_fork(skill_name, params, context, timeout)
        else:
            return await self._execute_inline(skill_name, params, context, timeout)
    
    async def _execute_inline(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext],
        timeout: Optional[float]
    ) -> SkillResult:
        """Inline execution - run in current context"""
        skill = self._registry.get(skill_name)
        if skill is None:
            return SkillResult(
                success=False,
                error=f"Skill not found: {skill_name}"
            )

        if not self._registry.is_enabled(skill_name):
            return SkillResult(
                success=False,
                error=f"Skill is disabled: {skill_name}"
            )

        execution_id = new_prefixed_id("run")
        record = ExecutionRecord(
            execution_id=execution_id,
            skill_name=skill_name,
            status="running",
            input_params=params,
            start_time=time.time()
        )
        self._executions[execution_id] = record

        if context is None:
            context = SkillContext(
                session_id=execution_id,
                user_id="system"
            )

        skill_info = self._registry.get(skill_name)
        if skill_info and hasattr(skill_info, '_config') and hasattr(skill_info._config, 'metadata'):
            tool_names = skill_info._config.metadata.get('tools', [])
            if tool_names:
                context.tools = list(tool_names)

        # Priority: explicit timeout > skill SKILL.md timeout > env var default
        effective_timeout = timeout
        if not effective_timeout:
            try:
                cfg = getattr(skill, '_config', None)
                meta = getattr(cfg, 'metadata', None) if cfg else None
                skill_timeout = meta.get('timeout') if isinstance(meta, dict) else None
                if skill_timeout is not None:
                    effective_timeout = float(skill_timeout)
            except Exception:
                pass
        if not effective_timeout:
            effective_timeout = self._default_timeout

        # Workflow check: if SKILL.md has steps:, execute as multi-step pipeline
        workflow_steps = None
        try:
            cfg = getattr(skill, '_config', None)
            meta = getattr(cfg, 'metadata', None) if cfg else None
            workflow_steps = meta.get('steps') if isinstance(meta, dict) else None
        except Exception:
            pass
        if isinstance(workflow_steps, list) and workflow_steps:
            from .skill_workflow_runner import get_workflow_runner
            runner = get_workflow_runner()
            result = await runner.execute_workflow(workflow_steps, params, context, timeout)
            record.status = "success" if result.success else "failed"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.output = result.output if result.success else None
            record.error = result.error
            self._registry.record_execution(skill_name, success=result.success, latency=record.latency)
            return result

        try:
            is_valid = await skill.validate(params)
            if not is_valid:
                record.status = "failed"
                record.end_time = time.time()
                record.error = "Parameter validation failed"
                record.latency = record.end_time - record.start_time
                self._registry.record_execution(skill_name, success=False, latency=record.latency)
                return SkillResult(success=False, error="Parameter validation failed")

            result = await asyncio.wait_for(
                sys_skill_call(
                    skill,
                    params,
                    context=context,
                    user_id=context.user_id,
                    session_id=context.session_id,
                ),
                timeout=effective_timeout
            )

            record.status = "success" if result.success else "failed"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.output = result.output if result.success else None
            record.error = result.error
            self._registry.record_execution(
                skill_name,
                success=result.success,
                latency=record.latency
            )
            return result

        except asyncio.TimeoutError:
            record.status = "timeout"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.error = f"Skill execution timed out after {effective_timeout}s"
            self._registry.record_execution(skill_name, success=False, latency=record.latency)
            return SkillResult(
                success=False,
                error=f"Skill execution timed out after {effective_timeout}s"
            )

        except Exception as e:
            record.status = "failed"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.error = str(e)
            self._registry.record_execution(skill_name, success=False, latency=record.latency)
            return SkillResult(success=False, error=str(e))

    async def execute_stream(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None,
    ) -> AsyncGenerator[SkillStreamEvent, None]:
        """Execute skill with streaming output."""
        skill = self._registry.get(skill_name)
        if skill is None:
            yield SkillStreamEvent(event_type="done", data=SkillResult(success=False, error=f"Skill not found: {skill_name}"), progress=1.0)
            return
        execution_id = new_prefixed_id("run")
        record = ExecutionRecord(
            execution_id=execution_id,
            skill_name=skill_name,
            status="running",
            input_params=params,
            start_time=time.time(),
        )
        self._executions[execution_id] = record
        if context is None:
            context = SkillContext(session_id=execution_id, user_id="system")
        try:
            async for event in skill.execute_stream(context, params):
                yield event
                if event.event_type == "done":
                    result = event.data if isinstance(event.data, SkillResult) else SkillResult(success=True, output=event.data)
                    record.status = "success" if result.success else "failed"
                    record.end_time = time.time()
                    record.latency = record.end_time - record.start_time
                    record.output = result.output if result.success else None
                    record.error = result.error
                    self._registry.record_execution(skill_name, success=result.success, latency=record.latency)
                    return
        except asyncio.TimeoutError:
            record.status = "timeout"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.error = "timeout"
            yield SkillStreamEvent(event_type="done", data=SkillResult(success=False, error=f"timeout: {timeout}s"), progress=1.0)
        except Exception as e:
            record.status = "failed"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.error = str(e)
            yield SkillStreamEvent(event_type="done", data=SkillResult(success=False, error=str(e)), progress=1.0)
    
    async def _execute_fork(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext],
        timeout: Optional[float]
    ) -> SkillResult:
        """Fork execution - spawn sub-agent for parallel execution."""
        skill = self._registry.get(skill_name)
        if not skill:
            return SkillResult(success=False, error=f"Skill not found: {skill_name}")

        effective_timeout = timeout or self._default_timeout

        async def run_in_fork():
            try:
                config = skill.get_config()
                prompt = params.get("prompt", params.get("input", ""))
                if not prompt and params:
                    prompt = str(params)

                from core.apps.agents.conversational import create_conversational_agent
                from core.harness.interfaces import AgentConfig, AgentContext

                # Prefer skill-injected model if available; otherwise use centralized resolution.
                model = getattr(skill, "_model", None)
                if model is None:
                    try:
                        from core.harness.utils.model_injection import create_selected_adapter
                        model = create_selected_adapter(model_name=(params.get("model") or best_model_for_purpose("chat")))
                    except Exception:
                        model = None

                if model is None:
                    return type(
                        "Result",
                        (),
                        {
                            "success": False,
                            "output": None,
                            "error": "Fork mode requires a configured LLM adapter (set LLM_PROVIDER/LLM_MODEL and provider API key env).",
                        },
                    )()

                sop_text = ""
                try:
                    meta = getattr(config, "metadata", None) or {}
                    if isinstance(meta, dict):
                        sop_text = meta.get("sop_markdown", "") or ""
                except Exception:
                    sop_text = ""

                sop_block = sop_text if sop_text else f"Skill: {skill_name}\n{config.description}"
                coding_profile = str((params or {}).get("_coding_policy_profile") or "").strip().lower()
                policy_block = ""
                if coding_profile == "karpathy_v1":
                    policy_block = (
                        "编码行为规范（karpathy_v1，必须遵循）：\n"
                        "1) 编码前思考：不要做未证实假设；遇到歧义/缺参，先列出需要确认的问题与可选方案。\n"
                        "2) 简洁优先：坚持最小可行实现；不要引入未经请求的抽象/架构/额外功能。\n"
                        "3) 精准修改：只改必须改的地方；避免无关格式化/无关文件改动。\n"
                        "4) 目标驱动：把任务转成可验证目标；给出验收标准（测试/复现步骤/检查清单）。\n"
                    )

                from core.harness.utils.prompt_loader import _sync_resolve
                system_prompt = _sync_resolve("skill-executor-fork",
                    sop=sop_block,
                )
                if policy_block:
                    system_prompt = policy_block + "\n" + system_prompt

                agent_config = AgentConfig(
                    name=f"fork-{skill_name}",
                    model=model_name,
                    metadata={"role": "fork-agent", "skill": skill_name},
                )
                # Use ReAct agent so fork mode can also orchestrate tools when provided.
                from core.apps.agents.react import create_react_agent
                agent = create_react_agent(config=agent_config, model=model)

                # Emit fork event for zero-black-box (parent=skill span, child=agent tree)
                try:
                    from core.services.execution_store import get_execution_store
                    import time as _t, uuid as _u
                    fork_span_id = f"fork:{skill_name}:{_u.uuid4().hex[:8]}"
                    store = get_execution_store()
                    await store.add_syscall_event({
                        "id": f"fork-{skill_name}-{_u.uuid4().hex[:8]}",
                        "span_id": fork_span_id,
                        "parent_span_id": f"skill:{skill_name}:start" if context else None,
                        "kind": "fork", "name": f"fork_{skill_name}", "status": "running",
                        "run_id": getattr(context, 'session_id', 'fork') or "fork",
                        "start_time": _t.time(),
                        "args": {"skill_name": skill_name, "model": str(getattr(agent, '_model', '') or '')},
                    })
                except Exception:
                    fork_span_id = None

                task = system_prompt + "\n\n用户输入：\n" + prompt
                agent_context = AgentContext(
                    session_id=context.session_id if context else "fork",
                    user_id=context.user_id if context else "system",
                    messages=[{"role": "user", "content": task}],
                    variables={"messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}], **(params or {})},
                    tools=list(getattr(context, "tools", []) or []) if context else [],
                )

                return await agent.execute(agent_context)

            except Exception as e:
                return type('Result', (), {'success': False, 'output': None, 'error': str(e)})()

        try:
            result = await asyncio.wait_for(run_in_fork(), timeout=effective_timeout)
            return SkillResult(
                success=result.success,
                output=result.output,
                error=result.error,
            )
        except asyncio.TimeoutError:
            return SkillResult(
                success=False,
                error=f"Fork execution timed out after {effective_timeout}s"
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Get execution record by ID"""
        return self._executions.get(execution_id)

    def list_executions(
        self,
        skill_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ExecutionRecord]:
        """List execution records"""
        records = list(self._executions.values())
        if skill_name:
            records = [r for r in records if r.skill_name == skill_name]
        records.sort(key=lambda r: r.start_time, reverse=True)
        return records[offset:offset + limit]

    def get_stats(self) -> Dict[str, Any]:
        """Get executor statistics"""
        total = len(self._executions)
        success = sum(1 for r in self._executions.values() if r.status == "success")
        failed = sum(1 for r in self._executions.values() if r.status == "failed")
        timeout = sum(1 for r in self._executions.values() if r.status == "timeout")
        return {
            "total_executions": total,
            "success_count": success,
            "failed_count": failed,
            "timeout_count": timeout,
            "success_rate": success / total if total > 0 else 0.0,
        }


# Global executor
_global_executor: Optional[SkillExecutor] = None


def get_skill_executor(discovery=None) -> SkillExecutor:
    """Get global skill executor
    
    Args:
        discovery: Optional SkillDiscovery instance for fork mode
    """
    global _global_executor
    if _global_executor is None:
        _global_executor = SkillExecutor(discovery=discovery)
    return _global_executor
