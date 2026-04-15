"""
Subagent Coordinator

Coordinates task execution across multiple Subagents.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
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
    """Coordinates execution of Subagents"""
    
    def __init__(self):
        self._registry = None
        self._active_instances: Dict[str, SubagentInstance] = {}
    
    async def _get_registry(self):
        if self._registry is None:
            self._registry = await get_subagent_registry()
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
            created_at=datetime.utcnow().isoformat()
        )
        
        self._active_instances[f"{session_id}:{name}"] = instance
        return instance
    
    async def execute_single(
        self,
        task: str,
        subagent_name: str,
        context: Optional[List[Dict]] = None
    ) -> SubagentResult:
        """Execute a single Subagent"""
        start_time = datetime.utcnow()
        
        try:
            instance = await self.create_instance(
                name=subagent_name,
                session_id=f"task-{datetime.utcnow().timestamp()}"
            )
            
            instance.state = "running"
            instance.started_at = datetime.utcnow().isoformat()
            
            # Add system prompt
            if instance.config.system_prompt:
                instance.add_message("system", instance.config.system_prompt)
            
            # Add task context
            if context:
                for msg in context:
                    instance.add_message(msg.get("role", "user"), msg.get("content", ""))
            
            # Add the actual task
            instance.add_message("user", task)
            
            # Check tool permissions
            available_tools = instance.config.allowed_tools
            denied_tools = instance.config.denied_tools
            
            logger.info(f"Executing Subagent '{subagent_name}' with tools: {available_tools}")
            logger.info(f"Denied tools: {denied_tools}")
            
            # Simulate execution (in real implementation, this would call the LLM)
            # Placeholder: Just acknowledge the task
            output = f"[Subagent: {subagent_name}] Task received. Available tools: {available_tools}"
            
            instance.state = "completed"
            instance.completed_at = datetime.utcnow().isoformat()
            
            duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return SubagentResult(
                subagent_name=subagent_name,
                success=True,
                output=output,
                tool_calls=instance.tool_calls,
                tokens_used=instance.tokens_used,
                duration_ms=duration
            )
            
        except Exception as e:
            logger.error(f"Subagent '{subagent_name}' failed: {e}")
            duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return SubagentResult(
                subagent_name=subagent_name,
                success=False,
                error=str(e),
                duration_ms=duration
            )
    
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