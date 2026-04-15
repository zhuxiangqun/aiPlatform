"""
Skill Evolution Module

Provides automatic skill capture, fix, and derivation capabilities.
"""

from .types import (
    EvolutionType,
    TriggerType,
    TriggerStatus,
    EvolutionTrigger,
    SkillVersion,
    EvolutionSuggestion,
    EvolutionResult,
    EvolutionConfig
)

from .lineage import (
    VersionLineage,
    get_version_lineage
)

from .engine import (
    EvolutionEngine,
    get_evolution_engine
)

from .triggers import (
    TriggerManager,
    get_trigger_manager,
    PostExecutionTrigger,
    ToolDegradationTrigger,
    MetricMonitorTrigger
)


__all__ = [
    # Types
    "EvolutionType",
    "TriggerType",
    "TriggerStatus",
    "EvolutionTrigger",
    "SkillVersion",
    "EvolutionSuggestion",
    "EvolutionResult",
    "EvolutionConfig",
    # Lineage
    "VersionLineage",
    "get_version_lineage",
    # Engine
    "EvolutionEngine",
    "get_evolution_engine",
    # Triggers
    "TriggerManager",
    "get_trigger_manager",
    "PostExecutionTrigger",
    "ToolDegradationTrigger",
    "MetricMonitorTrigger"
]