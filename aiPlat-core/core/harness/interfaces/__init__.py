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
    SkillStreamEvent,
)

from .loop import (
    ILoop,
    LoopState,
    LoopStateEnum,
    LoopConfig,
    LoopResult,
)

from .coordinator import (
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
    "SkillStreamEvent",
    
    # Loop
    "ILoop",
    "LoopState",
    "LoopStateEnum",
    "LoopConfig",
    "LoopResult",
    
    # Coordinator
    "CoordinationResult",
    "CoordinationConfig",
]