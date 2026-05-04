"""
Execution Module

Provides execution capabilities: loops, LangGraph, executors, retry, policy, feedback.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

__all__ = [
    # Loop
    "BaseLoop",
    "ReActLoop",
    "PlanExecuteLoop",
    "create_loop",
    
    # Retry
    "RetryConfig",
    "RetryManager",
    "RetryStrategy",
    "ExponentialBackoff",
    "create_retry_manager",
    
    # Policy
    "PolicyType",
    "PolicyConfig",
    "PolicyResult",
    "IPolicy",
    "TimeoutPolicy",
    "BudgetPolicy",
    "MaxStepsPolicy",
    "RateLimitPolicy",
    "PolicyEngine",
    "PolicyViolationError",
    "create_policy_engine",
    
    # Feedback
    "FeedbackType",
    "FeedbackSeverity",
    "FeedbackEntry",
    "FeedbackSummary",
    "FeedbackCollector",
    "ExecutionFeedback",
    "create_feedback",
    "execution_feedback",
    
    # LangGraph
    "ReActGraph",
    "ReActGraphConfig",
    "create_react_graph",
    "MultiAgentGraph",
    "MultiAgentConfig",
    "create_multi_agent_graph",
    "TriAgentGraph",
    "TriAgentConfig",
    "create_tri_agent_graph",
    "AgentState",
    "ExecutorConfig",
    "LangGraphExecutor",
    "execute_react",
    "execute_multi_agent",
    
    # Executor
    "ExecutionRequest",
    "ExecutionResponse",
    "UnifiedExecutor",
    "create_unified_executor",

    # Phase 5
    "EngineRouter",
]


# NOTE:
# This package used to eagerly import many submodules. That created large import graphs
# and circular dependencies (agents/skills/tools <-> execution <-> syscalls).
#
# To make architecture healthier (and improve startup robustness), we lazily resolve
# attributes on demand. Public API remains the same for callers.

_CANDIDATE_SUBMODULES = (
    "loop",
    "retry",
    "policy",
    "feedback",
    "langgraph",
    "executor",
    "router",
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
    # Import for type-checkers only (no runtime side effects).
    from .loop import BaseLoop, PlanExecuteLoop, ReActLoop, create_loop
    from .retry import ExponentialBackoff, RetryConfig, RetryManager, RetryStrategy, create_retry_manager
    from .policy import (
        BudgetPolicy,
        IPolicy,
        MaxStepsPolicy,
        PolicyConfig,
        PolicyEngine,
        PolicyResult,
        PolicyType,
        PolicyViolationError,
        RateLimitPolicy,
        TimeoutPolicy,
        create_policy_engine,
    )
    from .feedback import (
        ExecutionFeedback,
        FeedbackCollector,
        FeedbackEntry,
        FeedbackSeverity,
        FeedbackSummary,
        FeedbackType,
        create_feedback,
        execution_feedback,
    )
    from .langgraph import (
        AgentState,
        ExecutorConfig,
        LangGraphExecutor,
        MultiAgentConfig,
        MultiAgentGraph,
        ReActGraph,
        ReActGraphConfig,
        TriAgentConfig,
        TriAgentGraph,
        create_multi_agent_graph,
        create_react_graph,
        create_tri_agent_graph,
        execute_multi_agent,
        execute_react,
    )
    from .executor import ExecutionRequest, ExecutionResponse, UnifiedExecutor, create_unified_executor
    from .router import EngineRouter
