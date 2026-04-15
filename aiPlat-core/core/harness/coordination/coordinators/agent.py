"""
Coordinator Implementations Module

Provides coordinator implementations for multi-agent systems.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...interfaces.coordinator import (
    ICoordinator,
    CoordinationResult as ICoordinationResult,
    CoordinationConfig,
)
from ..patterns import (
    ICoordinationPattern,
    CoordinationContext,
    create_pattern,
)


@dataclass
class AgentCoordinatorConfig:
    """Agent coordinator configuration"""
    pattern: str = "pipeline"
    timeout: int = 60
    max_agents: int = 5


class BaseCoordinator(ABC):
    """
    Base coordinator abstract class
    """

    def __init__(self, config: Optional[AgentCoordinatorConfig] = None):
        self._config = config or AgentCoordinatorConfig()
        self._agents: List[Any] = []
        self._pattern: Optional[ICoordinationPattern] = None

    def add_agent(self, agent: Any) -> None:
        """Add agent to coordinator"""
        self._agents.append(agent)

    def remove_agent(self, agent_id: str) -> None:
        """Remove agent from coordinator"""
        self._agents = [a for a in self._agents if getattr(a, 'id', None) != agent_id]

    def get_agents(self) -> List[Any]:
        """Get all agents"""
        return self._agents.copy()

    def _build_context(self, task: Any) -> CoordinationContext:
        """Build coordination context"""
        return CoordinationContext(
            task=str(task),
            agents=self._agents,
            state={},
            metadata={"pattern": self._config.pattern}
        )


class SimpleCoordinator(BaseCoordinator):
    """
    Simple Coordinator
    
    Basic coordinator using a single pattern.
    """

    async def coordinate(
        self,
        task: Any,
        config: Optional[CoordinationConfig] = None
    ) -> ICoordinationResult:
        """Execute coordination"""
        # Create pattern if not exists
        if not self._pattern:
            self._pattern = create_pattern(self._config.pattern)
        
        # Build context
        context = self._build_context(task)
        
        # Execute coordination
        result = await self._pattern.coordinate(context)
        
        return ICoordinationResult(
            success=result.success,
            results=result.outputs,
            errors=result.errors,
            metadata=result.metadata
        )

    def set_pattern(self, pattern: ICoordinationPattern) -> None:
        """Set coordination pattern"""
        self._pattern = pattern


class AdaptiveCoordinator(BaseCoordinator):
    """
    Adaptive Coordinator
    
    Chooses coordination pattern based on task characteristics.
    """

    def __init__(self, config: Optional[AgentCoordinatorConfig] = None):
        super().__init__(config)
        self._pattern_cache: Dict[str, ICoordinationPattern] = {}

    async def coordinate(
        self,
        task: Any,
        config: Optional[CoordinationConfig] = None
    ) -> ICoordinationResult:
        """Execute adaptive coordination"""
        task_str = str(task).lower()
        
        # Select pattern based on task
        if any(kw in task_str for kw in ["parallel", "both", "all"]):
            pattern = create_pattern("fan_out_fan_in")
        elif any(kw in task_str for kw in ["review", "check", "validate"]):
            pattern = create_pattern("producer_reviewer")
        elif any(kw in task_str for kw in ["expert", "specialist"]):
            pattern = create_pattern("expert_pool")
        elif any(kw in task_str for kw in ["delegate", "manage"]):
            pattern = create_pattern("supervisor")
        else:
            pattern = create_pattern("pipeline")
        
        # Execute
        context = self._build_context(task)
        result = await pattern.coordinate(context)
        
        return ICoordinationResult(
            success=result.success,
            results=result.outputs,
            errors=result.errors,
            metadata={**result.metadata, "pattern": type(pattern).__name__}
        )


class HierarchicalCoordinator(BaseCoordinator):
    """
    Hierarchical Coordinator
    
    Multi-level coordination with supervisors and workers.
    """

    def __init__(self, config: Optional[AgentCoordinatorConfig] = None):
        super().__init__(config)
        self._supervisors: List[Any] = []
        self._workers: List[Any] = []

    def add_supervisor(self, agent: Any) -> None:
        """Add supervisor agent"""
        self._supervisors.append(agent)

    def add_worker(self, agent: Any) -> None:
        """Add worker agent"""
        self._workers.append(agent)

    async def coordinate(
        self,
        task: Any,
        config: Optional[CoordinationConfig] = None
    ) -> ICoordinationResult:
        """Execute hierarchical coordination"""
        if not self._supervisors:
            return ICoordinationResult(
                success=False,
                errors=["No supervisors configured"]
            )
        
        supervisor = self._supervisors[0]
        
        # Supervisors plan
        plan_prompt = f"Break down this task: {task}\n\nList subtasks for workers."
        try:
            plan_result = await supervisor.execute(plan_prompt)
            subtasks = plan_result.output if hasattr(plan_result, 'output') else str(plan_result)
        except Exception as e:
            return ICoordinationResult(
                success=False,
                errors=[f"Supervisor planning failed: {str(e)}"]
            )
        
        # Workers execute in parallel
        import asyncio
        tasks = [worker.execute(subtasks) for worker in self._workers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        outputs = [r.output if hasattr(r, 'output') else str(r) for r in results if not isinstance(r, Exception)]
        errors = [str(r) for r in results if isinstance(r, Exception)]
        
        # Supervisor synthesizes
        synthesis_prompt = f"Worker results:\n{chr(10).join(outputs)}\n\nSynthesize final answer."
        
        try:
            final_result = await supervisor.execute(synthesis_prompt)
            final_output = final_result.output if hasattr(final_result, 'output') else str(final_result)
        except Exception:
            final_output = "\n".join(outputs)
        
        return ICoordinationResult(
            success=len(errors) < len(self._workers),
            results=[final_output],
            errors=errors,
            metadata={"supervisors": len(self._supervisors), "workers": len(self._workers)}
        )


def create_coordinator(
    coordinator_type: str = "simple",
    config: Optional[AgentCoordinatorConfig] = None
) -> BaseCoordinator:
    """Factory function to create coordinator"""
    coordinators = {
        "simple": SimpleCoordinator,
        "adaptive": AdaptiveCoordinator,
        "hierarchical": HierarchicalCoordinator,
    }
    
    if coordinator_type not in coordinators:
        raise ValueError(f"Unknown coordinator type: {coordinator_type}")
    
    return coordinators[coordinator_type](config)