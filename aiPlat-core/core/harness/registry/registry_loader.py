"""
Entity Registry Loader — single source of truth for entity type definitions.

Replaces hardcoded agent_type/skill_type lists scattered across consumers.
All consumers MUST use load_agent_types() instead of if/elif chains.

Supports 7 entity types (YAML in ~/.aiplat/registry/):
  agents, skills, mcps, workflows, tools, domains
Plus 2 type definition files:
  agent_types, execution_types

arch_guard §87 + §88 enforce this module as the sole resolution path.

Usage:
    from core.harness.registry.registry_loader import (
        load_agent_types,
        load_entity_registry,
        auto_discover_and_register,
    )

    # Type resolution
    types = load_agent_types()
    canonical = types.resolve("plan")  # → "plan_execute"

    # Entity listing
    agents = load_entity_registry("agents")
    for a in agents:
        print(f"{a['id']}: {a['source']}")

    # Auto-discovery at startup
    new_count = auto_discover_and_register("agents", [
        "core/engine/agents",
        os.path.expanduser("~/.aiplat/agents"),
    ])
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml as _yaml

_log = logging.getLogger("aiplat.registry")

# Cache: {filepath: (mtime, data)}
_cache: Dict[str, tuple] = {}

# Supported entity types with their YAML key names
_ENTITY_TYPES = {
    "agents": "agents",
    "skills": "skills",
    "mcps": "mcps",
    "workflows": "workflows",
    "tools": "tools",
    "domains": "domains",
}


def _registry_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "registry"


def _engine_root() -> Path:
    """Return the engine directory (core/engine/)."""
    return Path(__file__).resolve().parent.parent.parent.parent / "engine"


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
        except OSError:  # noqa: cleanup-best-effort
            pass
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
        _log.warning("Unknown agent_type '%s' — falling back to conversational", agent_type)
        return "conversational"

    def is_valid(self, agent_type: str) -> bool:
        t = agent_type.lower().strip()
        return t in self.canonical or t in self.aliases

    def is_deprecated(self, agent_type: str) -> bool:
        return agent_type.lower().strip() in self.deprecated

    @property
    def all_valid(self) -> Set[str]:
        return set(self.canonical) | set(self.aliases.keys())


def load_agent_types(*, force_reload: bool = False) -> AgentTypeRegistry:
    """Load agent type definitions from agent_types.yaml (with caching)."""
    if force_reload:
        _cache.pop(str(_registry_home() / "agent_types.yaml"), None)
    data = _load_yaml(_registry_home() / "agent_types.yaml")
    if not data:
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


# ── Execution Types ────────────────────────────────────────────────────────


@dataclass
class ExecutionTypeRegistry:
    """Immutable snapshot of execution_types.yaml."""
    canonical: List[str] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)
    deprecated: List[str] = field(default_factory=list)

    def resolve(self, exec_type: str) -> str:
        if not exec_type:
            return "prompt"
        t = exec_type.lower().strip()
        if t in self.canonical:
            return t
        if t in self.aliases:
            return self.aliases[t]
        _log.warning("Unknown execution_type '%s' — falling back to prompt", exec_type)
        return "prompt"

    def is_valid(self, exec_type: str) -> bool:
        t = exec_type.lower().strip()
        return t in self.canonical or t in self.aliases


def load_execution_types(*, force_reload: bool = False) -> ExecutionTypeRegistry:
    if force_reload:
        _cache.pop(str(_registry_home() / "execution_types.yaml"), None)
    data = _load_yaml(_registry_home() / "execution_types.yaml")
    if not data:
        return ExecutionTypeRegistry(
            canonical=["prompt", "handler", "python_class", "tool_wrapper"],
            aliases={"llm": "prompt", "ai": "prompt", "script": "handler",
                     "code": "handler", "class": "python_class"},
            deprecated=["llm", "script"],
        )
    return ExecutionTypeRegistry(
        canonical=list(data.get("canonical", [])),
        aliases=dict(data.get("aliases", {})),
        deprecated=list(data.get("deprecated", [])),
    )


# ── Generic Entity Registry ────────────────────────────────────────────────


@dataclass
class RegistryConsistencyIssue:
    entity_type: str
    severity: str      # error | warning
    entity_id: str
    message: str


def load_entity_registry(entity_type: str, *, force_reload: bool = False) -> List[Dict[str, Any]]:
    """Load entity records from registry/{entity_type}.yaml.

    Args:
        entity_type: One of 'agents', 'skills', 'mcps', 'workflows', 'tools', 'domains'
    """
    if entity_type not in _ENTITY_TYPES:
        raise ValueError(f"Unknown entity type: {entity_type}. Valid: {list(_ENTITY_TYPES.keys())}")
    if force_reload:
        _cache.pop(str(_registry_home() / f"{entity_type}.yaml"), None)
    data = _load_yaml(_registry_home() / f"{entity_type}.yaml")
    if not data:
        return []
    key = _ENTITY_TYPES[entity_type]
    return list(data.get(key, []))


def _save_entity_registry(entity_type: str, records: List[Dict[str, Any]]) -> None:
    """Write entity records to registry/{entity_type}.yaml atomically."""
    filepath = _registry_home() / f"{entity_type}.yaml"
    _registry_home().mkdir(parents=True, exist_ok=True)
    tmp = str(filepath) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        _yaml.dump({_ENTITY_TYPES[entity_type]: records}, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    os.replace(tmp, str(filepath))
    _cache.pop(str(filepath), None)


def auto_discover_and_register(entity_type: str, scan_dirs: List[str] = None) -> int:
    """Scan directories for entities and register any not yet in the YAML.

    Returns: number of newly registered entities.
    """
    if entity_type not in _ENTITY_TYPES:
        return 0

    existing = load_entity_registry(entity_type)
    existing_ids = {r.get("id", "") for r in existing}

    if scan_dirs is None:
        scan_dirs = _default_scan_dirs(entity_type)

    new_records = []
    for scan_dir in scan_dirs:
        sp = Path(scan_dir).expanduser().resolve()
        if not sp.is_dir():
            continue
        source = "workspace" if str(sp).startswith(str(Path.home())) else "engine"
        for entry in sorted(sp.iterdir()):
            if not entry.is_dir() or entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            eid = entry.name
            if eid in existing_ids:
                continue
            # Detect entity definition file
            _def_file = _find_definition_file(entity_type, entry)
            if not _def_file:
                continue
            record = _build_record(entity_type, eid, source, entry, _def_file)
            if record:
                new_records.append(record)
                existing_ids.add(eid)

    if new_records:
        all_records = existing + new_records
        _save_entity_registry(entity_type, all_records)
        _log.info("auto_discover: registered %d new %s", len(new_records), entity_type)
    return len(new_records)


def verify_registry_consistency(entity_type: str, scan_dirs: List[str] = None) -> List[RegistryConsistencyIssue]:
    """Check registry against filesystem for orphans, duplicates, invalid paths.

    Returns list of issues (empty = clean).
    """
    issues = []
    records = load_entity_registry(entity_type, force_reload=True)
    registered_ids = {}
    for r in records:
        rid = r.get("id", "")
        if rid in registered_ids:
            issues.append(RegistryConsistencyIssue(
                entity_type, "error", rid,
                f"Duplicate entry in registry (also at index {registered_ids[rid]})"))
        else:
            registered_ids[rid] = records.index(r)

    # Check that every registered entity has a valid source_path
    for r in records:
        rid = r.get("id", "?")
        sp = r.get("source_path", "")
        src = r.get("source", "")
        # Code-defined entities don't need filesystem paths
        if src == "code":
            continue
        if not sp:
            issues.append(RegistryConsistencyIssue(entity_type, "warning", rid, "Missing source_path"))
            continue
        # Resolve relative paths
        resolved = _resolve_path(sp)
        if not resolved or not resolved.exists():
            issues.append(RegistryConsistencyIssue(
                entity_type, "warning", rid,
                f"source_path does not exist: {sp}"))

    # Check that every entity on disk has a registry entry (no orphans)
    if scan_dirs is None:
        scan_dirs = _default_scan_dirs(entity_type)
    for scan_dir in scan_dirs:
        sp = Path(scan_dir).expanduser().resolve()
        if not sp.is_dir():
            continue
        for entry in sorted(sp.iterdir()):
            if not entry.is_dir() or entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            eid = entry.name
            if eid not in registered_ids and _find_definition_file(entity_type, entry):
                issues.append(RegistryConsistencyIssue(
                    entity_type, "warning", eid,
                    f"Entity exists on disk but not in registry/{entity_type}.yaml — run auto_discover_and_register()"))

    return issues


# ── Internal Helpers ───────────────────────────────────────────────────────


def _default_scan_dirs(entity_type: str) -> List[str]:
    """Default directory scan paths for each entity type."""
    home = os.path.expanduser("~/.aiplat")
    engine = str(_engine_root())
    return {
        "agents":    [f"{engine}/agents", f"{home}/agents"],
        "skills":    [f"{engine}/skills", f"{home}/skills"],
        "mcps":      [f"{home}/mcps"],
        "workflows": [f"{home}/workflow_templates"],
        "tools":     [f"{engine}/../apps/tools"],
        "domains":   [f"{home}/ontologies"],
    }.get(entity_type, [])


def _find_definition_file(entity_type: str, entry_dir: Path) -> Optional[Path]:
    """Find the canonical definition file in an entity directory."""
    candidates = {
        "agents":    ["AGENT.md"],
        "skills":    ["SKILL.md"],
        "mcps":      ["server.yaml", "mcp.yaml", "config.yaml"],
        "workflows": ["workflow.yaml"],
        "tools":     ["tool.py", "base.py"],
        "domains":   [f"{entry_dir.name}.yaml"],
    }.get(entity_type, [])
    for c in candidates:
        p = entry_dir / c
        if p.exists():
            return p
    return None


def _build_record(entity_type: str, eid: str, source: str,
                  entry_dir: Path, def_file: Path) -> Optional[Dict[str, Any]]:
    """Build a registry record from a discovered entity."""
    record = {
        "id": eid,
        "source": source,
        "display_name": eid.replace("_", " ").title(),
        "source_path": _make_rel(str(def_file)),
        "status": "enabled",
    }
    # Try to parse frontmatter for AGENT.md / SKILL.md
    if def_file.suffix == ".md":
        try:
            raw = def_file.read_text(encoding="utf-8")
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    fm = _yaml.safe_load(parts[1]) or {}
                    record["display_name"] = str(fm.get("display_name") or fm.get("name") or record["display_name"])
                    if entity_type == "agents":
                        at = fm.get("agent_type", "")
                        if at:
                            record["agent_type"] = at
                    elif entity_type == "skills":
                        et = fm.get("execution_type", "")
                        if et:
                            record["execution_type"] = et
                        cat = fm.get("category", "")
                        if cat:
                            record["category"] = cat
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return record


def _resolve_path(source_path: str) -> Optional[Path]:
    """Resolve a source_path (may be relative to workspace root or ~/)."""
    p = Path(source_path).expanduser()
    if p.exists():
        return p
    # Try relative to workspace root
    ws = Path(__file__).resolve().parent.parent.parent.parent.parent
    p = ws / source_path
    if p.exists():
        return p
    # Try relative to core
    core = Path(__file__).resolve().parent.parent.parent.parent
    p = core / source_path
    if p.exists():
        return p
    return None


def _make_rel(source_path: str) -> str:
    """Make a path relative to workspace root where possible."""
    p = Path(source_path).expanduser().resolve()
    ws = Path(__file__).resolve().parent.parent.parent.parent.parent
    try:
        return str(p.relative_to(ws))
    except ValueError:  # noqa: best-effort-parse
        pass
    home = Path.home()
    try:
        return "~/" + str(p.relative_to(home))
    except ValueError:
        return source_path


__all__ = [
    "AgentTypeRegistry",
    "ExecutionTypeRegistry",
    "RegistryConsistencyIssue",
    "load_agent_types",
    "load_execution_types",
    "load_entity_registry",
    "auto_discover_and_register",
    "verify_registry_consistency",
]
