"""
Execution Module

Provides execution capabilities: loops, LangGraph, executors, retry, policy, feedback.
"""

from .loop import (
    BaseLoop,
    ReActLoop,
    PlanExecuteLoop,
    create_loop,
)

from .retry import (
    RetryConfig,
    RetryManager,
    RetryStrategy,
    ExponentialBackoff,
    create_retry_manager,
)

from .policy import (
    PolicyType,
    PolicyConfig,
    PolicyResult,
    IPolicy,
    TimeoutPolicy,
    BudgetPolicy,
    MaxStepsPolicy,
    RateLimitPolicy,
    PolicyEngine,
    PolicyViolationError,
    create_policy_engine,
)

from .feedback import (
    FeedbackType,
    FeedbackSeverity,
    FeedbackEntry,
    FeedbackSummary,
    FeedbackCollector,
    ExecutionFeedback,
    create_feedback,
    execution_feedback,
)

from .langgraph import (
    ReActGraph,
    ReActGraphConfig,
    create_react_graph,
    MultiAgentGraph,
    MultiAgentConfig,
    create_multi_agent_graph,
    TriAgentGraph,
    TriAgentConfig,
    create_tri_agent_graph,
    AgentState,
    ExecutorConfig,
    LangGraphExecutor,
    execute_react,
    execute_multi_agent,
)

from .executor import (
    ExecutionRequest,
    ExecutionResponse,
    UnifiedExecutor,
    create_unified_executor,
)

# Phase 5: EngineRouter (minimal)
from .router import EngineRouter

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
