"""
Skills Module

Provides skill implementations: Base, TextGeneration, CodeGeneration, DataAnalysis,
with enhanced registry, executor, and automatic discovery system.
"""

from .base import (
    BaseSkill,
    SkillMetadata,
    TextGenerationSkill,
    CodeGenerationSkill,
    DataAnalysisSkill,
    create_skill,
)

from .registry import (
    SkillRegistry,
    SkillVersion,
    SkillBindingStats,
    get_skill_registry,
)

from .executor import (
    SkillExecutor,
    ExecutionRecord,
    get_skill_executor,
)

from .discovery import (
    DiscoveredSkill,
    SKILLMD_parser,
    SkillDiscovery,
    SkillLoader,
    SkillMatcher,
    create_discovery,
    create_loader,
)

from .types import (
    SkillCategory,
    ExecutionMode,
    SkillManifest,
    SandboxConfig,
    ScriptResult,
)

from .script_runner import (
    ScriptRunner,
    get_script_runner,
)

from .evolution import (
    EvolutionEngine,
    EvolutionConfig,
    TriggerManager,
    get_evolution_engine,
    get_trigger_manager,
    get_version_lineage,
)

__all__ = [
    # Base classes
    "BaseSkill",
    "SkillMetadata",
    "TextGenerationSkill",
    "CodeGenerationSkill",
    "DataAnalysisSkill",
    "create_skill",
    # Registry
    "SkillRegistry",
    "SkillVersion",
    "SkillBindingStats",
    "get_skill_registry",
    # Executor
    "SkillExecutor",
    "ExecutionRecord",
    "get_skill_executor",
    # Discovery
    "DiscoveredSkill",
    "SKILLMD_parser",
    "SkillDiscovery",
    "SkillLoader",
    "SkillMatcher",
    "create_discovery",
    "create_loader",
    # Types
    "SkillCategory",
    "ExecutionMode",
    "SkillManifest",
    "SandboxConfig",
    "ScriptResult",
    "ScriptRunner",
    "get_script_runner",
    # Evolution
    "EvolutionEngine",
    "EvolutionConfig",
    "TriggerManager",
    "get_evolution_engine",
    "get_trigger_manager",
    "get_version_lineage",
]