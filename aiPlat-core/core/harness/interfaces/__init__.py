"""
Harness Interfaces - Core Contract Definitions

This module defines the core interfaces that all implementations must follow.
These interfaces provide the contract layer for the aiPlat-core framework.
"""

from .agent import (
    IAgent,
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentStatus,
)

from .tool import (
    ITool,
    ToolSchema,
    ToolConfig,
    ToolResult,
)

from .skill import (
    ISkill,
    SkillConfig,
    SkillContext,
    SkillResult,
)

from .loop import (
    ILoop,
    LoopState,
    LoopStateEnum,
    LoopConfig,
    LoopResult,
)

from .coordinator import (
    ICoordinator,
    CoordinationResult,
    CoordinationConfig,
)

__all__ = [
    # Agent
    "IAgent",
    "AgentConfig",
    "AgentContext",
    "AgentResult",
    "AgentStatus",
    
    # Tool
    "ITool",
    "ToolSchema",
    "ToolConfig",
    "ToolResult",
    
    # Skill
    "ISkill",
    "SkillConfig",
    "SkillContext",
    "SkillResult",
    
    # Loop
    "ILoop",
    "LoopState",
    "LoopStateEnum",
    "LoopConfig",
    "LoopResult",
    
    # Coordinator
    "ICoordinator",
    "CoordinationResult",
    "CoordinationConfig",
]