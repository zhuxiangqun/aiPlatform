"""
Plan-Execute Agent Module

Provides Plan-Execute agent implementation.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .base import BaseAgent, AgentMetadata
from ...harness.interfaces import (
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentStatus,
    LoopState,
)
from ...adapters.llm import ILLMAdapter


@dataclass
class PlanStep:
    """Plan step"""
    id: int
    description: str
    status: str = "pending"  # pending, executing, completed, failed
    result: Any = None


@dataclass
class PlanExecuteAgentConfig:
    """Plan-Execute agent configuration"""
    max_planning_steps: int = 5
    max_execution_steps: int = 10
    enable_replanning: bool = True
    replan_on_error: bool = True


class PlanExecuteAgent(BaseAgent):
    """
    Plan-Execute Agent
    
    Implements two-phase execution:
    - Planning: Analyze task and create execution plan
    - Execution: Execute plan step by step
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        tools: Optional[List[Any]] = None,
        agent_config: Optional[PlanExecuteAgentConfig] = None,
        **kwargs
    ):
        self._pe_config = agent_config or PlanExecuteAgentConfig()
        self._tools = tools or []
        self._plan: List[PlanStep] = []
        
        super().__init__(
            config=config,
            model=model,
            loop_type="plan_execute",
            **kwargs
        )
        
        self._metadata = AgentMetadata(
            name="PlanExecuteAgent",
            description="Plan then execute agent",
            version="1.0.0",
            capabilities=["planning", "execution", "replanning"],
            supported_loop_types=["plan_execute"]
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute Plan-Execute agent via Harness loop delegation.
        
        Delegates to BaseAgent.execute() which runs the PlanExecuteLoop,
        with model injected before execution.
        """
        if self._loop and hasattr(self._loop, 'set_model') and self._model:
            self._loop.set_model(self._model)
        
        return await super().execute(context)


def create_plan_execute_agent(
    config: AgentConfig,
    model: Optional[ILLMAdapter] = None,
    tools: Optional[List[Any]] = None,
    **kwargs
) -> PlanExecuteAgent:
    """Create Plan-Execute agent"""
    return PlanExecuteAgent(config=config, model=model, tools=tools, **kwargs)
