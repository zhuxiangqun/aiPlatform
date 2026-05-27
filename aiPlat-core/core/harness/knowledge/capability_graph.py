"""
AI Capability Graph — pure factual reflection of the system's AI capability inventory.

Builds nodes + edges from 5 dimensions:
  - Agents  (AGENT.md frontmatter)
  - Skills  (SKILL.md frontmatter)
  - Tools   (ToolRegistry)
  - MCP Servers (MCPManager)
  - Workflows   (PipelineStageConfig from ExecutionStore)

Zero analysis.  Graph/Analysis separation (CLAUDE.md principle).
Analysis consumers (health, unused detection, impact) live in capability_health.py.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Helpers (shared with skill_deps.py)
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> Dict[str, Any]:
    """Extract YAML frontmatter from AGENT.md / SKILL.md files.

    Uses yaml.safe_load for proper nested YAML support.
    Falls back to a simple line-by-line parser if yaml is unavailable.
    """
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    raw = parts[1].strip()
    if not raw:
        return {}
    # Try proper YAML parser first
    try:
        import yaml as _yaml
        data = _yaml.safe_load(raw)
        if isinstance(data, dict):
            # Normalize scalar values that should be lists
            for key in ('required_skills', 'required_tools', 'skills', 'tools',
                        'tags', 'effects', 'mcp_servers'):
                if key in data and isinstance(data[key], str):
                    data[key] = [data[key]]
            return {str(k): v for k, v in data.items()}
    except Exception:
        pass
    # Fallback: simple line parser (handles flat key: value format)
    fm: Dict[str, Any] = {}
    for line in raw.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip().strip("'\"")
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
        elif val in ("true", "false", "yes", "no"):
            fm[key] = val in ("true", "yes")
        elif val.isdigit():
            fm[key] = int(val)
        else:
            fm[key] = val
    return fm


def _find_engine_dir(*parts: str) -> Optional[Path]:
    """Locate core/engine/ directory relative to this file."""
    here = Path(__file__).resolve()
    for _ in range(6):
        candidate = here.parent
        if (candidate / "core" / "engine").exists():
            return candidate / "core" / "engine" / Path(*parts)
        here = here.parent
    # Fallback: import core
    try:
        import core as _core
        if hasattr(_core, '__file__') and _core.__file__:
            return Path(os.path.dirname(_core.__file__)) / "engine" / Path(*parts)
    except Exception:
        pass
    return None


def _extract_syscalls_from_sop(body: str) -> List[str]:
    """Heuristic extraction of syscall references from SKILL.md body."""
    calls: Set[str] = set()
    for m in re.finditer(r'sys_(\w+)_(\w+)', body):
        calls.add(f"sys_{m.group(1)}_{m.group(2)}")
    for m in re.finditer(r'sys_(\w+)', body):
        calls.add(f"sys_{m.group(1)}")
    return sorted(calls)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class CapabilityGraphResult:
    created_at: float
    nodes: Dict[str, Dict[str, Any]]   # id -> node
    edges: List[Dict[str, str]]         # [{from, to, relation}]


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_capability_graph() -> CapabilityGraphResult:
    """Scan all 5 capability dimensions and return a pure graph.

    Returns:
        CapabilityGraphResult with:
          - nodes keyed by ``{type}:{name}`` (e.g. ``agent:architect``)
          - edges with ``relation`` field:
            * ``requires``     agent→skill, agent→tool
            * ``uses``         skill→syscall
            * ``provides``     mcp_server→tool
            * ``maps_to``      workflow→agent, workflow→skill
    """
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, str]] = []

    _scan_agents(nodes, edges)
    _scan_skills(nodes, edges)
    _scan_tools(nodes, edges)
    _scan_mcp_servers(nodes, edges)
    _scan_workflows(nodes, edges)

    return CapabilityGraphResult(
        created_at=time.time(),
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Dimension scanners
# ---------------------------------------------------------------------------

def _scan_agents(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan core/engine/agents/*/AGENT.md."""
    agents_root = _find_engine_dir("agents")
    if not agents_root or not agents_root.exists():
        return

    for agent_dir in sorted(agents_root.iterdir()):
        if not agent_dir.is_dir():
            continue
        md_file = agent_dir / "AGENT.md"
        if not md_file.exists():
            continue
        agent_id = agent_dir.name
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        fm = _parse_frontmatter(text)

        nodes[f"agent:{agent_id}"] = {
            "id": f"agent:{agent_id}",
            "type": "agent",
            "label": fm.get("name", agent_id),
            "raw_id": agent_id,
            "agent_type": fm.get("agent_type", fm.get("type", "")),
            "status": fm.get("status", "unknown"),
            "category": fm.get("category", ""),
            "tags": fm.get("tags", []),
            "path": str(agent_dir),
        }

        # agent → skill edges (accept required_skills OR skills field)
        skill_refs = fm.get("required_skills") or fm.get("skills") or []
        if isinstance(skill_refs, str):
            skill_refs = [skill_refs]
        for skill_ref in skill_refs:
            edges.append({"from": f"agent:{agent_id}", "to": f"skill:{skill_ref}", "relation": "requires"})

        # agent → tool edges
        tool_refs = fm.get("required_tools") or fm.get("tools") or []
        if isinstance(tool_refs, str):
            tool_refs = [tool_refs]
        for tool_ref in tool_refs:
            edges.append({"from": f"agent:{agent_id}", "to": f"tool:{tool_ref}", "relation": "requires"})


def _scan_skills(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan core/engine/skills/*/SKILL.md."""
    skills_root = _find_engine_dir("skills")
    if not skills_root or not skills_root.exists():
        return

    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        md_file = skill_dir / "SKILL.md"
        if not md_file.exists():
            continue
        skill_id = skill_dir.name
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        fm = _parse_frontmatter(text)
        body = text.split("---", 2)[2] if text.count("---") >= 2 else text

        deps = _extract_syscalls_from_sop(body)

        nodes[f"skill:{skill_id}"] = {
            "id": f"skill:{skill_id}",
            "type": "skill",
            "label": fm.get("name", skill_id),
            "raw_id": skill_id,
            "category": fm.get("category", ""),
            "status": fm.get("status", "unknown"),
            "effects": fm.get("effects", []),
            "syscalls_used": deps,
            "path": str(skill_dir),
        }

        # skill → syscall edges
        for syscall_name in deps:
            edges.append({"from": f"skill:{skill_id}", "to": f"syscall:{syscall_name}", "relation": "uses"})


def _scan_tools(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan ToolRegistry for registered tools."""
    try:
        from core.apps.tools.base import get_tool_registry
        reg = get_tool_registry()
        tool_names = reg.list_tools()
        for name in sorted(tool_names):
            tool = reg.get(name)
            desc = getattr(tool, 'description', '') if tool else ''
            category = getattr(tool, 'category', '') if tool else ''

            nodes[f"tool:{name}"] = {
                "id": f"tool:{name}",
                "type": "tool",
                "label": name,
                "raw_id": name,
                "description": str(desc)[:200],
                "category": str(category) if category else "",
            }

            # MCP tools: edge from server → tool
            if name.startswith("mcp."):
                parts = name.split(".", 2)
                if len(parts) >= 2:
                    server_name = parts[1]
                    edges.append({"from": f"mcp_server:{server_name}", "to": f"tool:{name}", "relation": "provides"})
    except Exception:
        pass


def _scan_mcp_servers(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan MCPManager for configured MCP servers."""
    try:
        from core.management.mcp_manager import MCPManager as _MCPMgr
        mgr = _MCPMgr()
        servers = mgr.list_servers()
        for srv in servers:
            name = srv.name
            nodes[f"mcp_server:{name}"] = {
                "id": f"mcp_server:{name}",
                "type": "mcp_server",
                "label": name,
                "raw_id": name,
                "enabled": getattr(srv, 'enabled', True),
                "transport": getattr(srv, 'transport', ''),
                "url": getattr(srv, 'url', ''),
            }
    except Exception:
        pass


def _scan_workflows(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan ExecutionStore for active pipeline workflows."""
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        store = getattr(rt, 'execution_store', None) if rt else None
        if not store:
            return
        active = getattr(store, '_active', {}) or {}
        for run_id, run_data in active.items():
            wf_id = run_id[:16] if isinstance(run_id, str) else str(run_id)
            stages = run_data.get("stages", []) if isinstance(run_data, dict) else []
            if isinstance(run_data, dict):
                stages = run_data.get("stages", run_data.get("stages_config", [])) or []
                wf_label = run_data.get("name", run_data.get("pipeline_name", wf_id))
            else:
                wf_label = wf_id

            nodes[f"workflow:{wf_id}"] = {
                "id": f"workflow:{wf_id}",
                "type": "workflow",
                "label": str(wf_label)[:80],
                "raw_id": str(run_id),
            }

            for stage in stages:
                agent_id = stage.get("agent_id", "") if isinstance(stage, dict) else ""
                if agent_id:
                    edges.append({"from": f"workflow:{wf_id}", "to": f"agent:{agent_id}", "relation": "maps_to"})
                skills = stage.get("required_skills", stage.get("skills", [])) if isinstance(stage, dict) else []
                for skill_ref in (skills or []):
                    edges.append({"from": f"workflow:{wf_id}", "to": f"skill:{skill_ref}", "relation": "maps_to"})
    except Exception:
        pass
