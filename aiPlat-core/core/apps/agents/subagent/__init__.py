"""
Subagent Module

Provides Subagent architecture for task isolation and permission control.
"""

from .config import (
    ToolPermissionLevel,
    SubagentConfig,
    SubagentInstance,
    BUILTIN_SUBAGENTS
)

from .registry import (
    SubagentRegistry,
    get_subagent_registry,
    initialize_registry
)

from .coordinator import (
    ExecutionStrategy,
    SubagentResult,
    SubagentCoordinator,
    get_subagent_coordinator
)


__all__ = [
    # Config
    "ToolPermissionLevel",
    "SubagentConfig",
    "SubagentInstance",
    "BUILTIN_SUBAGENTS",
    # Registry
    "SubagentRegistry",
    "get_subagent_registry",
    "initialize_registry",
    # Coordinator
    "ExecutionStrategy",
    "SubagentResult",
    "SubagentCoordinator",
    "get_subagent_coordinator"
]