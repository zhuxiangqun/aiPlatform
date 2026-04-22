"""
Skills Module

IMPORTANT:
This package intentionally avoids eager imports of heavy submodules (executor/syscalls).
Otherwise, importing *any* `core.apps.skills.*` can trigger deep syscall/gate chains and
cause circular imports (especially during policy gate initialization).

We expose the same public API via lazy attribute loading.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

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

_LAZY_ATTRS = {
    # base
    "BaseSkill": ("core.apps.skills.base", "BaseSkill"),
    "SkillMetadata": ("core.apps.skills.base", "SkillMetadata"),
    "TextGenerationSkill": ("core.apps.skills.base", "TextGenerationSkill"),
    "CodeGenerationSkill": ("core.apps.skills.base", "CodeGenerationSkill"),
    "DataAnalysisSkill": ("core.apps.skills.base", "DataAnalysisSkill"),
    "create_skill": ("core.apps.skills.base", "create_skill"),
    # registry
    "SkillRegistry": ("core.apps.skills.registry", "SkillRegistry"),
    "SkillVersion": ("core.apps.skills.registry", "SkillVersion"),
    "SkillBindingStats": ("core.apps.skills.registry", "SkillBindingStats"),
    "get_skill_registry": ("core.apps.skills.registry", "get_skill_registry"),
    # executor
    "SkillExecutor": ("core.apps.skills.executor", "SkillExecutor"),
    "ExecutionRecord": ("core.apps.skills.executor", "ExecutionRecord"),
    "get_skill_executor": ("core.apps.skills.executor", "get_skill_executor"),
    # discovery
    "DiscoveredSkill": ("core.apps.skills.discovery", "DiscoveredSkill"),
    "SKILLMD_parser": ("core.apps.skills.discovery", "SKILLMD_parser"),
    "SkillDiscovery": ("core.apps.skills.discovery", "SkillDiscovery"),
    "SkillLoader": ("core.apps.skills.discovery", "SkillLoader"),
    "SkillMatcher": ("core.apps.skills.discovery", "SkillMatcher"),
    "create_discovery": ("core.apps.skills.discovery", "create_discovery"),
    "create_loader": ("core.apps.skills.discovery", "create_loader"),
    # types
    "SkillCategory": ("core.apps.skills.types", "SkillCategory"),
    "ExecutionMode": ("core.apps.skills.types", "ExecutionMode"),
    "SkillManifest": ("core.apps.skills.types", "SkillManifest"),
    "SandboxConfig": ("core.apps.skills.types", "SandboxConfig"),
    "ScriptResult": ("core.apps.skills.types", "ScriptResult"),
    # script runner
    "ScriptRunner": ("core.apps.skills.script_runner", "ScriptRunner"),
    "get_script_runner": ("core.apps.skills.script_runner", "get_script_runner"),
    # evolution
    "EvolutionEngine": ("core.apps.skills.evolution", "EvolutionEngine"),
    "EvolutionConfig": ("core.apps.skills.evolution", "EvolutionConfig"),
    "TriggerManager": ("core.apps.skills.evolution", "TriggerManager"),
    "get_evolution_engine": ("core.apps.skills.evolution", "get_evolution_engine"),
    "get_trigger_manager": ("core.apps.skills.evolution", "get_trigger_manager"),
    "get_version_lineage": ("core.apps.skills.evolution", "get_version_lineage"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_ATTRS:
        mod, attr = _LAZY_ATTRS[name]
        return getattr(import_module(mod), attr)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + list(_LAZY_ATTRS.keys())))
