"""
ReAct Agent Module

Provides ReAct (Reasoning + Acting) agent implementation.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .base import BaseAgent, AgentMetadata
from ...harness.interfaces import (
    AgentConfig,
    AgentContext,
    AgentResult,
    LoopConfig,
)
from ...harness.infrastructure.hooks import HookManager
from ...adapters.llm import ILLMAdapter


@dataclass
class ReActAgentConfig:
    """ReAct agent configuration"""
    max_steps: int = 10
    max_tokens: int = 4096
    temperature: float = 0.7
    enable_reflection: bool = True
    tool_choice: str = "auto"  # auto, force, none


class ReActAgent(BaseAgent):
    """
    ReAct Agent
    
    Implements Reasoning + Acting pattern:
    - Think about what action to take
    - Execute the action
    - Observe the result
    - Repeat until done
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        tools: Optional[List[Any]] = None,
        loop_config: Optional[ReActAgentConfig] = None,
        hook_manager: Optional[HookManager] = None
    ):
        self._react_config = loop_config or ReActAgentConfig()
        self._tools = tools or []
        self._hook_manager = hook_manager or HookManager()
        
        # Create ReAct loop
        loop_cfg = LoopConfig(
            max_steps=self._react_config.max_steps,
            max_tokens=self._react_config.max_tokens,
        )
        
        super().__init__(
            config=config,
            model=model,
            loop_type="react",
            loop_config=loop_cfg
        )
        
        self._metadata = AgentMetadata(
            name="ReActAgent",
            description="Reasoning + Acting agent",
            version="1.0.0",
            capabilities=["reasoning", "tool_use", "reflection"],
            supported_loop_types=["react"]
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute ReAct agent via Harness loop delegation.
        
        Delegates to BaseAgent.execute() which runs the ReActLoop,
        with model/skills/tools injected before execution.
        """
        # Inject tools into loop before running
        if self._loop and hasattr(self._loop, 'set_tools') and self._tools:
            from ...apps.tools.base import get_tool_registry
            tool_registry = get_tool_registry()
            resolved_tools = []
            for tool_name in context.tools if context.tools else []:
                tool = tool_registry.get(tool_name)
                if tool:
                    resolved_tools.append(tool)
            resolved_tools.extend(self._tools)
            self._loop.set_tools(resolved_tools)
        
        # Delegate to BaseAgent.execute() which runs the loop
        return await super().execute(context)

    def add_tool(self, tool: Any) -> None:
        """Add tool to agent"""
        self._tools.append(tool)


def create_react_agent(
    config: AgentConfig,
    model: Optional[ILLMAdapter] = None,
    tools: Optional[List[Any]] = None,
    **kwargs
) -> ReActAgent:
    """Create ReAct agent"""
    return ReActAgent(config=config, model=model, tools=tools, **kwargs)
