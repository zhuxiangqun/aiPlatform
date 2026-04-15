"""
Agent Base Module

Provides base Agent class implementing IAgent interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...harness.interfaces import (
    IAgent,
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentStatus,
    LoopConfig,
)
from ...harness.execution import create_loop
from ...adapters.llm import ILLMAdapter, LLMConfig


@dataclass
class AgentMetadata:
    """Agent metadata"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    supported_loop_types: List[str] = field(default_factory=list)


class BaseAgent(IAgent):
    """
    Base Agent Implementation
    
    Provides common functionality for all agent implementations.
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        loop_type: str = "react",
        loop_config: Optional[LoopConfig] = None
    ):
        self._config = config
        self._model = model
        self._status = AgentStatus.IDLE
        self._loop = None
        self._current_context: Optional[AgentContext] = None
        
        # Initialize execution loop
        self._loop = create_loop(
            loop_type=loop_type,
            config=loop_config or LoopConfig()
        )

    async def initialize(self, config: AgentConfig) -> None:
        """Initialize agent with configuration"""
        self._config = config
        self._status = AgentStatus.INITIALIZING
        
        # Initialize model if not provided
        if not self._model and config.metadata.get("model"):
            from ...adapters.llm import create_adapter
            provider = config.metadata.get("provider", "openai")
            self._model = create_adapter(
                provider=provider,
                api_key=config.metadata.get("api_key"),
                model=config.model,
                base_url=config.metadata.get("base_url"),
            )
        
        self._status = AgentStatus.IDLE

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute agent with given context"""
        self._status = AgentStatus.RUNNING
        self._current_context = context
        
        try:
            # Prepare initial state
            from ...harness.interfaces import LoopState
            state = LoopState(
                context={
                    "task": context.messages[-1].get("content", "") if context.messages else "",
                    "session_id": context.session_id,
                    "user_id": context.user_id,
                    **context.variables
                },
                step_count=0
            )
            
            # Inject model, skills, and tools into the loop before running
            if self._loop:
                if hasattr(self._loop, 'set_model') and self._model:
                    self._loop.set_model(self._model)
                if hasattr(self._loop, 'set_tools') and hasattr(self, '_tools'):
                    from ...apps.tools.base import get_tool_registry
                    tool_registry = get_tool_registry()
                    resolved_tools = []
                    for tool_name in context.tools if context.tools else []:
                        tool = tool_registry.get(tool_name)
                        if tool:
                            resolved_tools.append(tool)
                    if hasattr(self, '_tools') and self._tools:
                        resolved_tools.extend(self._tools)
                    self._loop.set_tools(resolved_tools)
                if hasattr(self._loop, 'set_skills') and hasattr(self, '_skills'):
                    from ...apps.skills import get_skill_registry
                    skill_registry = get_skill_registry()
                    resolved_skills = []
                    for skill_name in context.skills if context.skills else []:
                        skill = skill_registry.get(skill_name)
                        if skill:
                            resolved_skills.append(skill)
                    if hasattr(self, '_skills') and self._skills:
                        resolved_skills.extend(self._skills)
                    self._loop.set_skills(resolved_skills)
                
                result = await self._loop.run(state, LoopConfig())
                
                return AgentResult(
                    success=result.success,
                    output=result.output,
                    error=result.error,
                    metadata={
                        "steps": result.final_state.step_count if result.final_state else 0,
                        "loop_type": type(self._loop).__name__,
                    },
                    token_usage={"total": result.final_state.used_tokens if result.final_state else 0}
                )
            else:
                return AgentResult(
                    success=False,
                    error="No execution loop initialized"
                )
                
        except Exception as e:
            self._status = AgentStatus.ERROR
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )
        finally:
            if self._status != AgentStatus.ERROR:
                self._status = AgentStatus.COMPLETED

    async def cleanup(self) -> None:
        """Cleanup resources"""
        self._status = AgentStatus.IDLE
        self._current_context = None
        
        if self._loop:
            await self._loop.reset()

    def get_status(self) -> AgentStatus:
        """Get current agent status"""
        return self._status

    async def pause(self) -> None:
        """Pause agent execution"""
        if self._status == AgentStatus.RUNNING:
            self._status = AgentStatus.PAUSED

    async def resume(self) -> AgentContext:
        """Resume agent execution"""
        self._status = AgentStatus.RUNNING
        return self._current_context

    def get_config(self) -> AgentConfig:
        """Get agent configuration"""
        return self._config

    def get_model(self) -> Optional[ILLMAdapter]:
        """Get model adapter"""
        return self._model


class ConfigurableAgent(BaseAgent):
    """
    Configurable Agent
    
    Agent that can be configured at runtime.
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        tools: Optional[List[Any]] = None,
        skills: Optional[List[Any]] = None,
        **kwargs
    ):
        super().__init__(config, model, **kwargs)
        self._tools = tools or []
        self._skills = skills or []

    def add_tool(self, tool: Any) -> None:
        """Add tool to agent"""
        self._tools.append(tool)

    def remove_tool(self, tool_name: str) -> None:
        """Remove tool from agent"""
        self._tools = [t for t in self._tools if getattr(t, 'name', '') != tool_name]

    def add_skill(self, skill: Any) -> None:
        """Add skill to agent"""
        self._skills.append(skill)

    def get_tools(self) -> List[Any]:
        """Get agent tools"""
        return self._tools

    def get_skills(self) -> List[Any]:
        """Get agent skills"""
        return self._skills


def create_agent(
    agent_type: str = "base",
    config: Optional[AgentConfig] = None,
    **kwargs
) -> IAgent:
    """
    Factory function to create agent
    
    Args:
        agent_type: Type of agent ("base", "react", "plan_execute", "conversational", "multi_agent")
        config: Agent configuration
        **kwargs: Additional arguments
        
    Returns:
        IAgent: Agent instance
    """
    from .react import ReActAgent
    from .plan_execute import PlanExecuteAgent
    from .conversational import ConversationalAgent
    from .multi_agent import MultiAgent
    
    if config is None:
        config = AgentConfig(name="default")
    
    type_map = {
        "react": "react",
        "plan": "plan_execute",
        "plan_execute": "plan_execute",
        "conversational": "conversational",
        "multi_agent": "multi_agent",
        "rag": "rag",
        "tool": "react",
        "base": "base",
    }
    
    resolved_type = type_map.get(agent_type, "base")
    
    if resolved_type == "react":
        return ReActAgent(config=config, **kwargs)
    elif resolved_type == "plan_execute":
        return PlanExecuteAgent(config=config, **kwargs)
    elif resolved_type == "conversational":
        return ConversationalAgent(config=config, **kwargs)
    elif resolved_type == "multi_agent":
        return MultiAgent(config=config, **kwargs)
    elif resolved_type == "rag":
        from .rag import RAGAgent
        return RAGAgent(config=config, **kwargs)
    else:
        return BaseAgent(config=config, **kwargs)