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

    def __init__(self):
        self._registry = None
        self._active_instances: Dict[str, SubagentInstance] = {}
    
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
        context: Optional[List[Dict]] = None
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
                for msg in context:
                    messages.append({
                        "role": msg.get("role", "user"),
                        "content": str(msg.get("content", "")),
                    })
            messages.append({"role": "user", "content": task})

            # Create agent and bind allowed tools
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
            from core.harness.interfaces.agent import AgentContext
            agent_ctx = AgentContext(
                session_id=f"subagent-{subagent_name}",
                user_id="subagent_coordinator",
                messages=messages,
            )
            result = await agent.execute(agent_ctx)

            if result.success:
                output = result.output or ""
                if isinstance(output, dict):
                    output = output.get("content", str(output))
                # Summarize per §5.26: parent needs concise summary, not full output
                summarized = self._summarize_output(str(output), max_chars=800)
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
    def _summarize_output(output: str, max_chars: int = 800) -> str:
        if len(output) <= max_chars:
            return output
        return output[:max_chars] + f"\n\n... [truncated from {len(output)} chars]"
    
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


def get_subagent_coordinator() -> SubagentCoordinator:
    """Get global Subagent coordinator"""
    global _coordinator
    if _coordinator is None:
        _coordinator = SubagentCoordinator()
    return _coordinator


__all__ = [
    "ExecutionStrategy",
    "SubagentResult",
    "SubagentCoordinator",
    "get_subagent_coordinator"
]