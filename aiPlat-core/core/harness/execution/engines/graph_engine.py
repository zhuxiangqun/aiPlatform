"""
GraphEngine (Phase 9 P2).

Wraps LangGraph graphs as IExecutionEngine with checkpoint/restore.
Uses the internal CompiledGraph engine for consistent trace/callback integration.
"""

from __future__ import annotations
import logging

from typing import Any, Dict, Optional

from ..langgraph.graphs.react import ReActGraph, ReActGraphConfig
from ..langgraph.graphs.planning import PlanningGraph, PlanningGraphConfig
from ..langgraph.graphs.multi_agent import MultiAgentGraph, MultiAgentGraphConfig
from ..langgraph.graphs.reflection import ReflectionGraph, ReflectionGraphConfig
from ..langgraph.graphs.tri_agent import TriAgentGraph, TriAgentGraphConfig
from ...kernel.types import ExecutionResult


_GRAPH_SPECS: Dict[str, tuple] = {
    "react": (ReActGraph, ReActGraphConfig),
    "planning": (PlanningGraph, PlanningGraphConfig),
    "multi_agent": (MultiAgentGraph, MultiAgentGraphConfig),
    "reflection": (ReflectionGraph, ReflectionGraphConfig),
    "tri_agent": (TriAgentGraph, TriAgentGraphConfig),
}


class GraphEngine:
    name = "graph"

    def __init__(self, graph_type: str = "react", **config_kwargs):
        if graph_type not in _GRAPH_SPECS:
            graph_type = "react"
        graph_cls, config_cls = _GRAPH_SPECS[graph_type]
        cfg = config_cls(**config_kwargs)
        self._graph = graph_cls(cfg)
        self._graph_type = graph_type

    async def execute_agent(self, agent: Any, context: Any) -> Any:
        state = self._build_initial_state(agent, context)
        try:
            result_state = await self._graph.run(state)
        except Exception as e:
            return ExecutionResult(ok=False, error=f"GraphEngine[{self._graph_type}]: {str(e)[:200]}", http_status=500)
        return self._wrap_result(result_state)

    def _build_initial_state(self, agent: Any, context: Any) -> Dict[str, Any]:
        state: Dict[str, Any] = {"messages": [], "context": {}, "metadata": {}}
        try:
            msgs = getattr(context, "messages", None) or []
            state["messages"] = list(msgs)
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        try:
            vars0 = dict(getattr(context, "variables", {}) or {})
            state["context"] = vars0
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        return state

    def _wrap_result(self, state: Dict[str, Any]) -> Any:
        observation = str(state.get("observation", "") or "")
        reasoning = str(state.get("reasoning", "") or "")
        output = observation or reasoning or "Graph execution completed"
        return ExecutionResult(ok=True, payload={"output": output, "state": state})
