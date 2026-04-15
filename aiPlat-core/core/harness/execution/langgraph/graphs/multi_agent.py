"""
LangGraph Multi-Agent Graph

Implements multi-agent coordination using LangGraph.
"""

from typing import Any, Dict, List, Optional, TypedDict
from dataclasses import dataclass, field

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from .react import ReActGraph, ReActGraphConfig
from ....interfaces.coordinator import CoordinationConfig


@dataclass
class MultiAgentConfig:
    """Multi-agent configuration"""
    num_agents: int = 3
    coordination_config: Optional[CoordinationConfig] = None
    convergence_threshold: float = 0.8
    max_rounds: int = 5
    model: Optional[Any] = None
    tools: List[Any] = field(default_factory=list)


class MultiAgentState(TypedDict, total=False):
    """Multi-agent coordination state"""
    task: str
    agent_results: List[Dict[str, Any]]
    current_round: int
    converged: bool
    final_result: Any
    context: Dict[str, Any]


class MultiAgentGraph:
    """
    Multi-Agent Graph Implementation
    
    Coordinates multiple agents to solve a task.
    """

    def __init__(self, config: Optional[MultiAgentConfig] = None):
        self._config = config or MultiAgentConfig()
        self._agents: List[ReActGraph] = []
        self._graph = None
        
        self._create_agents()
        
        if LANGGRAPH_AVAILABLE:
            self._build_graph()

    def _create_agents(self) -> None:
        """Create agent instances"""
        for i in range(self._config.num_agents):
            agent_config = ReActGraphConfig(
                max_steps=self._config.coordination_config.max_rounds if self._config.coordination_config else 5,
                model=self._config.model,
                tools=self._config.tools
            )
            self._agents.append(ReActGraph(agent_config))

    def _build_graph(self) -> None:
        """Build LangGraph for multi-agent coordination"""
        if not LANGGRAPH_AVAILABLE:
            return
        
        workflow = StateGraph(MultiAgentState)
        
        workflow.add_node("distribute", self._distribute_task)
        workflow.add_node("execute", self._execute_agents)
        workflow.add_node("aggregate", self._aggregate_results)
        workflow.add_node("evaluate", self._evaluate_convergence)
        
        workflow.set_entry_point("distribute")
        workflow.add_edge("distribute", "execute")
        workflow.add_edge("execute", "aggregate")
        workflow.add_conditional_edges(
            "evaluate",
            self._should_continue,
            {
                "continue": "distribute",
                "finish": END
            }
        )
        
        self._graph = workflow.compile()

    async def _distribute_task(self, state: MultiAgentState) -> Dict[str, Any]:
        """Distribute task to agents"""
        state.current_round += 1
        return {"current_round": state.current_round}

    async def _execute_agents(self, state: MultiAgentState) -> Dict[str, Any]:
        """Execute all agents"""
        results = []
        
        for i, agent in enumerate(self._agents):
            result = await agent.run({
                "messages": [{"role": "user", "content": state.task}],
                "context": {"round": state.current_round}
            })
            results.append({
                "agent_id": i,
                "result": result.observation if hasattr(result, 'observation') else str(result),
                "reasoning": result.reasoning if hasattr(result, 'reasoning') else ""
            })
        
        return {"agent_results": results}

    async def _aggregate_results(self, state: MultiAgentState) -> Dict[str, Any]:
        """Aggregate results from agents"""
        if not state.agent_results:
            return {}
        
        # Simple aggregation: concatenate observations
        aggregated = "\n---".join([
            r.get("result", "")
            for r in state.agent_results
        ])
        
        return {"context": {"aggregated": aggregated}}

    async def _evaluate_convergence(self, state: MultiAgentState) -> Dict[str, Any]:
        """Evaluate convergence of agent results"""
        if len(state.agent_results) < 2:
            return {"converged": False}
        
        # Simple convergence check: compare observations
        results = [r.get("result", "") for r in state.agent_results]
        
        # Check similarity (simplified)
        if len(set(results)) == 1:
            return {
                "converged": True,
                "final_result": results[0]
            }
        
        # Check if max rounds reached
        if state.current_round >= self._config.max_rounds:
            return {
                "converged": True,
                "final_result": state.agent_results[0].get("result", "")
            }
        
        return {"converged": False}

    def _should_continue(self, state: MultiAgentState) -> str:
        """Determine if continue or finish"""
        if state.converged:
            return "finish"
        
        if state.current_round >= self._config.max_rounds:
            return "finish"
        
        return "continue"

    async def run(self, task: str) -> MultiAgentState:
        """
        Run multi-agent coordination
        
        Args:
            task: Task to solve
            
        Returns:
            MultiAgentState: Final state
        """
        initial_state = MultiAgentState(task=task)
        
        if LANGGRAPH_AVAILABLE and self._graph:
            result = await self._graph.ainvoke(initial_state)
            return result
        
        # Fallback execution
        return await self._run_fallback(task)

    async def _run_fallback(self, task: str) -> MultiAgentState:
        """Fallback execution without LangGraph"""
        state = MultiAgentState(task=task)
        
        while state.current_round < self._config.max_rounds and not state.converged:
            state.current_round += 1
            
            # Execute all agents
            results = []
            for i, agent in enumerate(self._agents):
                result = await agent.run({
                    "messages": [{"role": "user", "content": task}],
                })
                results.append({
                    "agent_id": i,
                    "result": result.observation if hasattr(result, 'observation') else str(result)
                })
            
            state.agent_results = results
            
            # Evaluate convergence
            if len(set([r.get("result", "") for r in results])) == 1:
                state.converged = True
                state.final_result = results[0].get("result", "")
                break
        
        if not state.final_result:
            state.final_result = state.agent_results[0].get("result", "") if state.agent_results else ""
        
        return state


def create_multi_agent_graph(
    num_agents: int = 3,
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    max_rounds: int = 5
) -> MultiAgentGraph:
    """
    Create multi-agent graph
    
    Args:
        num_agents: Number of agents
        model: Language model
        tools: List of tools
        max_rounds: Maximum coordination rounds
        
    Returns:
        MultiAgentGraph: Configured multi-agent graph
    """
    config = MultiAgentConfig(
        num_agents=num_agents,
        max_rounds=max_rounds,
        model=model,
        tools=tools or []
    )
    return MultiAgentGraph(config)