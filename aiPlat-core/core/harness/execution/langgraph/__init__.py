"""
LangGraph Module

Provides LangGraph-based graph implementations for agent execution.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

__all__ = [
    # Core
    "GraphState",
    "NodeType",
    "NodeResult",
    "GraphConfig",
    "ExecutionTrace",
    "GraphBuilder",
    "CompiledGraph",
    "create_graph_builder",
    
    # Callbacks
    "CallbackEvent",
    "CallbackContext",
    "CallbackHandler",
    "CallbackRegistry",
    "CallbackManager",
    "LoggingCallback",
    "MetricsCallback",
    "create_callback_manager",
    "create_logging_callback",
    "create_metrics_callback",
    
    # Graphs
    "ReActGraph",
    "ReActGraphConfig",
    "create_react_graph",
    "MultiAgentGraph",
    "MultiAgentConfig",
    "create_multi_agent_graph",
    "TriAgentGraph",
    "TriAgentConfig",
    "create_tri_agent_graph",
    
    # Executor
    "ExecutorConfig",
    "LangGraphExecutor",
    "ExecutionTimeoutError",
    "ExecutionError",
    "execute_react",
    "execute_multi_agent",
]


# Avoid eager imports to prevent circular dependencies with agents/skills.
_CANDIDATE_SUBMODULES = (
    "core",
    "callbacks",
    "graphs",
    "nodes",
    "executor",
)


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    for mod in _CANDIDATE_SUBMODULES:
        m = importlib.import_module(f"{__name__}.{mod}")
        if hasattr(m, name):
            return getattr(m, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))


if TYPE_CHECKING:
    from .core import CompiledGraph, ExecutionTrace, GraphBuilder, GraphConfig, GraphState, NodeResult, NodeType, create_graph_builder
    from .callbacks import (
        CallbackContext,
        CallbackEvent,
        CallbackHandler,
        CallbackManager,
        CallbackRegistry,
        LoggingCallback,
        MetricsCallback,
        create_callback_manager,
        create_logging_callback,
        create_metrics_callback,
    )
    from .graphs import (
        MultiAgentConfig,
        MultiAgentGraph,
        ReActGraph,
        ReActGraphConfig,
        TriAgentConfig,
        TriAgentGraph,
        create_multi_agent_graph,
        create_react_graph,
        create_tri_agent_graph,
    )
    from .executor import ExecutionError, ExecutionTimeoutError, ExecutorConfig, LangGraphExecutor, execute_multi_agent, execute_react
