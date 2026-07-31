"""
Entity Registry Loader — single source of truth for entity type definitions.

Replaces hardcoded agent_type/skill_type lists scattered across 5 consumers.
All consumers MUST use load_agent_types() instead of if/elif chains.
arch_guard §87 enforces this.

Usage:
    from core.harness.registry.registry_loader import load_agent_types

    types = load_agent_types()
    canonical = types.resolve("plan")       # → "plan_execute"
    is_valid = types.is_valid("react")      # → True
    is_deprecated = types.is_deprecated("subagent")  # → True
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml as _yaml

_log = logging.getLogger("aiplat.registry")

# Cache: {filepath: (mtime, data)}
_cache: Dict[str, tuple] = {}


def _registry_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "registry"


def _load_yaml(filepath: Path, ttl_seconds: float = 60.0) -> Optional[Dict[str, Any]]:
    """Load YAML with mtime-based cache."""
    key = str(filepath)
    now = time.time()
    cached = _cache.get(key)
    if cached:
        cached_mtime, cached_data = cached
        try:
            actual_mtime = os.path.getmtime(filepath)
            if actual_mtime == cached_mtime and now - cached_data.get("_loaded_at", 0) < ttl_seconds:
                return cached_data
        except OSError:
            pass  # file doesn't exist, fall through to reload
    try:
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        data["_loaded_at"] = now
        _cache[key] = (os.path.getmtime(filepath), data)
        return data
    except Exception as e:
        _log.warning("Failed to load registry %s: %s", filepath, e)
        return None


# ── Agent Types ────────────────────────────────────────────────────────────


@dataclass
class AgentTypeRegistry:
    """Immutable snapshot of agent_types.yaml."""
    canonical: List[str] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)
    deprecated: List[str] = field(default_factory=list)

    def resolve(self, agent_type: str) -> str:
        """Resolve an agent_type string to its canonical form."""
        if not agent_type:
            return "conversational"
        t = agent_type.lower().strip()
        if t in self.canonical:
            return t
        if t in self.aliases:
            resolved = self.aliases[t]
            _log.debug("agent_type '%s' resolved to canonical '%s'", agent_type, resolved)
            return resolved
        # Unknown type: default to conversational
        _log.warning("Unknown agent_type '%s' — falling back to conversational", agent_type)
        return "conversational"

    def is_valid(self, agent_type: str) -> bool:
        """Check if a type is valid (canonical or alias)."""
        t = agent_type.lower().strip()
        return t in self.canonical or t in self.aliases

    def is_deprecated(self, agent_type: str) -> bool:
        """Check if a type is deprecated."""
        return agent_type.lower().strip() in self.deprecated

    @property
    def all_valid(self) -> Set[str]:
        """All valid agent types (canonical + alias keys)."""
        return set(self.canonical) | set(self.aliases.keys())


def load_agent_types(*, force_reload: bool = False) -> AgentTypeRegistry:
    """Load agent type definitions from agent_types.yaml (with caching).

    Returns a snapshot — changes to the YAML file require a cache miss
    (mtime change or TTL expiry) to be reflected.
    """
    if force_reload:
        _cache.pop(str(_registry_home() / "agent_types.yaml"), None)
    data = _load_yaml(_registry_home() / "agent_types.yaml")
    if not data:
        # Fallback: hardcoded minimum set used before registry existed
        _log.warning("agent_types.yaml not found, using built-in fallback")
        return AgentTypeRegistry(
            canonical=["conversational", "react", "plan_execute"],
            aliases={"plan": "plan_execute", "reflection": "plan_execute",
                     "tool": "react", "tool_using": "react", "subagent": "react",
                     "pure_agent": "conversational"},
            deprecated=["subagent", "pure_agent"],
        )
    return AgentTypeRegistry(
        canonical=list(data.get("canonical", [])),
        aliases=dict(data.get("aliases", {})),
        deprecated=list(data.get("deprecated", [])),
    )


__all__ = [
    "AgentTypeRegistry",
    "load_agent_types",
]
