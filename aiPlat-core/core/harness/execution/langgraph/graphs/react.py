"""
LangGraph ReAct Graph

Implements the ReAct (Reasoning + Acting) agent using LangGraph.
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from ..nodes import (
    AgentState,
    ReasonNode,
    ActNode,
    ObserveNode,
    create_reason_node,
    create_act_node,
    create_observe_node,
)
from ....interfaces.loop import LoopConfig


@dataclass
class ReActGraphConfig:
    """ReAct graph configuration"""
    max_steps: int = 10
    max_tokens: int = 8192
    model: Optional[Any] = None
    tools: List[Any] = field(default_factory=list)
    enable_observation_processing: bool = True


class ReActGraph:
    """
    ReAct Graph Implementation
    
    Implements the ReAct pattern using LangGraph:
    - Reason node: LLM decides action
    - Act node: Execute action
    - Observe node: Process result
    """

    def __init__(self, config: Optional[ReActGraphConfig] = None):
        self._config = config or ReActGraphConfig()
        self._graph = None
        self._nodes = {}
        
        if LANGGRAPH_AVAILABLE:
            self._build_graph()

    def _build_graph(self) -> None:
        """Build LangGraph"""
        # Create nodes
        self._nodes["reason"] = create_reason_node(
            model=self._config.model,
            tools=self._config.tools
        )
        self._nodes["act"] = create_act_node(
            model=self._config.model,
            tools=self._config.tools
        )
        self._nodes["observe"] = create_observe_node(
            model=self._config.model,
            tools=self._config.tools,
            process_observation=self._config.enable_observation_processing
        )
        
        # Build graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("reason", self._reason_wrapper)
        workflow.add_node("act", self._act_wrapper)
        workflow.add_node("observe", self._observe_wrapper)
        
        # Add edges
        workflow.set_entry_point("reason")
        workflow.add_edge("reason", "act")
        workflow.add_edge("act", "observe")
        workflow.add_conditional_edges(
            "observe",
            self._should_continue,
            {
                "continue": "reason",
                "finish": END
            }
        )
        
        self._graph = workflow.compile()

    async def _reason_wrapper(self, state: AgentState) -> Dict[str, Any]:
        """Wrapper for reason node"""
        return await self._nodes["reason"].execute(state)

    async def _act_wrapper(self, state: AgentState) -> Dict[str, Any]:
        """Wrapper for act node"""
        return await self._nodes["act"].execute(state)

    async def _observe_wrapper(self, state: AgentState) -> Dict[str, Any]:
        """Wrapper for observe node"""
        return await self._nodes["observe"].execute(state)

    def _should_continue(self, state: AgentState) -> str:
        """Determine if continue or finish"""
        observation = state.observation.upper()
        
        if "DONE" in observation:
            return "finish"
        
        if state.step_count >= self._config.max_steps:
            return "finish"
        
        return "continue"

    async def run(self, initial_state: Optional[Dict[str, Any]] = None) -> AgentState:
        """
        Run the ReAct graph
        
        Args:
            initial_state: Initial state dictionary
            
        Returns:
            AgentState: Final state
        """
        if not LANGGRAPH_AVAILABLE:
            return await self._run_fallback(initial_state)
        
        # Create initial state
        state = AgentState(
            messages=initial_state.get("messages", []) if initial_state else [],
            context=initial_state.get("context", {}) if initial_state else {},
        )
        
        # Run graph
        result = await self._graph.ainvoke(state)
        
        return result

    async def _run_fallback(self, initial_state: Optional[Dict[str, Any]]) -> AgentState:
        """Fallback execution without LangGraph"""
        state = AgentState(
            messages=initial_state.get("messages", []) if initial_state else [],
            context=initial_state.get("context", {}) if initial_state else {},
        )
        
        while state.step_count < self._config.max_steps:
            # Reason
            reason_result = await self._nodes["reason"].execute(state)
            state.reasoning = reason_result.get("reasoning", "")
            state.step_count = reason_result.get("step_count", state.step_count)
            
            # Act
            act_result = await self._nodes["act"].execute(state)
            state.action = act_result.get("action", "")
            state.observation = act_result.get("observation", "")
            
            # Observe
            observe_result = await self._nodes["observe"].execute(state)
            state.observation = observe_result.get("observation", state.observation)
            
            # Check termination
            if "DONE" in state.observation.upper():
                break
        
        return state


def create_react_graph(
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    max_steps: int = 10
) -> ReActGraph:
    """
    Create ReAct graph
    
    Args:
        model: Language model
        tools: List of tools
        max_steps: Maximum steps
        
    Returns:
        ReActGraph: Configured ReAct graph
    """
    config = ReActGraphConfig(
        max_steps=max_steps,
        model=model,
        tools=tools or []
    )
    return ReActGraph(config)