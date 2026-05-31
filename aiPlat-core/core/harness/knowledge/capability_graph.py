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
# Graph builder — with SQLite persistence + incremental sync
# ---------------------------------------------------------------------------

_CAP_CACHE: Optional[CapabilityGraphResult] = None
_CAP_CACHE_TS: float = 0.0
_CAP_CACHE_LOCK: Any = None


def build_capability_graph() -> CapabilityGraphResult:
    """Scan all 5 capability dimensions and return a pure graph.

    Persisted to SQLite for restart survival. Incremental sync via mtime on
    AGENT.md / SKILL.md files (≤10 changes → rebuild only changed directories).

    Returns:
        CapabilityGraphResult with nodes + edges.
    """
    global _CAP_CACHE, _CAP_CACHE_TS, _CAP_CACHE_LOCK

    if _CAP_CACHE_LOCK is None:
        import threading as _th
        _CAP_CACHE_LOCK = _th.Lock()

    # Try SQLite persistence first
    try:
        from core.harness.knowledge.cap_graph_persist import has_cache as _has, load_nodes as _ln, load_edges as _le, init_db as _idb
        _idb()
        if _has():
            nodes = _ln()
            edges = _le()

            # Incremental sync: check mtimes of AGENT.md/SKILL.md files
            stale_ids: List[str] = []
            for nid, n in nodes.items():
                fpath = n.get("path", "")
                if not fpath or not os.path.exists(fpath):
                    continue
                # Check AGENT.md or SKILL.md modification
                md_file = os.path.join(fpath, "AGENT.md")
                if not os.path.exists(md_file):
                    md_file = os.path.join(fpath, "SKILL.md")
                if not os.path.exists(md_file):
                    continue
                current_mtime = os.path.getmtime(md_file)
                if abs(current_mtime - n.get("_mtime", 0)) > 0.001:
                    stale_ids.append(nid)

            if 0 < len(stale_ids) <= 10:
                # Incremental: remove stale, re-scan only those
                for sid in stale_ids:
                    ntype = nodes[sid].get("type", "")
                    if sid in nodes:
                        del nodes[sid]
                edges = [e for e in edges if e["from"] not in stale_ids and e["to"] not in stale_ids]
                # Rebuild only for stale types
                _incremental_rescan(nodes, edges, stale_ids)
                _finalize(nodes, edges)
                return _cache_and_return(nodes, edges)

            if len(stale_ids) > 10:
                pass  # fall through to full rebuild below
            else:
                # 0 stale: compute degrees and return
                _finalize(nodes, edges)
                return _cache_and_return(nodes, edges)
    except Exception:
        pass

    # Full rebuild (first run or >10 stale)
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, str]] = []

    _scan_agents(nodes, edges)
    _scan_skills(nodes, edges)
    _scan_tools(nodes, edges)
    _scan_mcp_servers(nodes, edges)
    _scan_workflows(nodes, edges)
    _scan_entry_points(nodes, edges)

    _finalize(nodes, edges)
    _save_cap_graph(nodes, edges)
    return _cache_and_return(nodes, edges)


def _incremental_rescan(nodes, edges, stale_ids):
    """Rescan only directories for stale nodes."""
    stale_types = set()
    for sid in stale_ids:
        if sid.startswith("agent:"):
            stale_types.add("agent")
        elif sid.startswith("skill:"):
            stale_types.add("skill")
        elif sid.startswith("tool:"):
            stale_types.add("tool")
        elif sid.startswith("mcp_server:"):
            stale_types.add("mcp")
        elif sid.startswith("workflow:"):
            stale_types.add("workflow")
    if "agent" in stale_types:
        _scan_agents(nodes, edges)
    if "skill" in stale_types:
        _scan_skills(nodes, edges)
    if "tool" in stale_types:
        _scan_tools(nodes, edges)
    if "mcp" in stale_types:
        _scan_mcp_servers(nodes, edges)
    if "workflow" in stale_types:
        _scan_workflows(nodes, edges)


def _finalize(nodes, edges):
    """Compute degrees for all nodes."""
    for nid, n in nodes.items():
        n["in_degree"] = sum(1 for e in edges if e["to"] == nid)
        n["out_degree"] = sum(1 for e in edges if e["from"] == nid)
        # Update mtime from filesystem
        fpath = n.get("path", "")
        if fpath and os.path.exists(fpath):
            for md_name in ("AGENT.md", "SKILL.md"):
                mdp = os.path.join(fpath, md_name)
                if os.path.exists(mdp):
                    n["_mtime"] = os.path.getmtime(mdp)
                    break


def _save_cap_graph(nodes, edges):
    """Persist to SQLite."""
    try:
        from core.harness.knowledge.cap_graph_persist import save_graph
        save_graph(nodes, edges)
    except Exception:
        pass


def _cache_and_return(nodes, edges):
    """Save to in-memory cache and return CapabilityGraphResult."""
    result = CapabilityGraphResult(created_at=time.time(), nodes=nodes, edges=edges)
    global _CAP_CACHE, _CAP_CACHE_TS, _CAP_CACHE_LOCK
    if _CAP_CACHE_LOCK is None:
        import threading as _th
        _CAP_CACHE_LOCK = _th.Lock()
    with _CAP_CACHE_LOCK:
        _CAP_CACHE = result
        _CAP_CACHE_TS = time.time()
    return result


def clear_capability_cache():
    """Invalidate both in-memory cache and SQLite persistence (called by hot-reload)."""
    global _CAP_CACHE, _CAP_CACHE_TS
    lock = _CAP_CACHE_LOCK
    if lock:
        with lock:
            _CAP_CACHE = None
            _CAP_CACHE_TS = 0.0
    else:
        _CAP_CACHE = None
        _CAP_CACHE_TS = 0.0
    # Clear SQLite so next build re-indexes
    try:
        import os as _os
        from core.harness.knowledge.cap_graph_persist import _db_path
        path = _db_path()
        if _os.path.exists(path):
            _os.remove(path)
    except Exception:
        pass


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
        from core.harness.integration import get_tool_registry
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
    """Scan MCPManager for configured MCP servers (engine + workspace)."""
    try:
        from core.management.mcp_manager import MCPManager as _MCPMgr
        for scope in ("engine", "workspace"):
            mgr = _MCPMgr(scope=scope)
            for srv in mgr.list_servers():
                name = srv.name
                nodes[f"mcp_server:{name}"] = {
                    "id": f"mcp_server:{name}",
                    "type": "mcp_server",
                    "label": name,
                    "raw_id": name,
                    "enabled": getattr(srv, 'enabled', True),
                    "transport": getattr(srv, 'transport', ''),
                    "url": getattr(srv, 'url', ''),
                    "command": getattr(srv, 'command', ''),
                    "args": getattr(srv, 'args', []) or [],
                    "scope": scope,
                    "status": "unknown",
                }
        _probe_mcp_reachability(nodes)
    except Exception:
        pass


def _probe_mcp_reachability(nodes: Dict[str, Dict[str, Any]]):
    """Lightweight connectivity check for MCP servers. Best-effort, 1s timeout."""
    import urllib.request
    import shutil
    import subprocess

    for key, node in list(nodes.items()):
        if node.get("type") != "mcp_server":
            continue
        if not node.get("enabled", True):
            node["status"] = "disabled"
            continue

        transport = node.get("transport", "")
        try:
            if transport == "sse":
                url = node.get("url", "")
                if not url:
                    node["status"] = "unreachable"
                    continue
                if "/mcp" in url:
                    # Probe: try to open a stream; just check if host:port is reachable
                    try:
                        with urllib.request.urlopen(url, timeout=1):
                            pass
                        node["status"] = "reachable"
                    except Exception as e:
                        # Reachable but not a real MCP SSE endpoint
                        node["status"] = "unreachable"
                        node["status_detail"] = str(e)[:120]
                else:
                    node["status"] = "unreachable"
                    node["status_detail"] = "url does not contain /mcp path"

            elif transport == "stdio":
                cmd = node.get("command", "")
                if not cmd:
                    node["status"] = "unreachable"
                    continue
                if shutil.which(cmd):
                    # For npx-based MCPs, also check if the npm package exists
                    if cmd == "npx":
                        args = node.get("args", []) or []
                        for arg in args:
                            if arg.startswith("@") or (not arg.startswith("-") and "/" not in arg):
                                try:
                                    r = subprocess.run(
                                        ["npm", "view", arg, "version"],
                                        capture_output=True, timeout=3,
                                    )
                                    if r.returncode == 0:
                                        node["status"] = "reachable"
                                    else:
                                        node["status"] = "unreachable"
                                        node["status_detail"] = f"npm package not found: {arg}"
                                except Exception:
                                    node["status"] = "unreachable"
                                    node["status_detail"] = f"failed to check npm package: {arg}"
                                break
                        else:
                            node["status"] = "reachable"
                    else:
                        node["status"] = "reachable"
                else:
                    node["status"] = "unreachable"
                    node["status_detail"] = f"command not found: {cmd}"

            else:
                node["status"] = "unreachable"
                node["status_detail"] = f"unsupported transport: {transport}"
        except Exception:
            node["status"] = "unreachable"


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


def _scan_entry_points(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan API routers for duplicate entry points serving the same capability."""
    import re as _re
    from pathlib import Path as _Py

    here = _Py(__file__).resolve()
    for _ in range(5):
        routers_dir = here.parent.parent.parent / "api" / "routers"
        if routers_dir.exists():
            break
        here = here.parent
    else:
        return

    capability_patterns: Dict[str, Any] = {
        "agent.execute": _re.compile(r'@router\.\w+\([\"\'][\w/]*agents?/[\w{}_]*execute'),
        "agent.create": _re.compile(r'@router\.\w+\([\"\'][\w/]*agents?[\"\']'),
        "skill.execute": _re.compile(r'@router\.\w+\([\"\'][\w/]*skills?/[\w{}_]*execute'),
        "sfp.injection": _re.compile(r'system_prompt|_sys_prompt'),
    }

    found: Dict[str, List[str]] = {}
    for py_file in sorted(routers_dir.glob("*.py")):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for cap_name, pattern in capability_patterns.items():
            if pattern.search(content):
                found.setdefault(cap_name, []).append(str(py_file.name))

    for cap_name, files in found.items():
        node_id = f"entry_point:{cap_name}"
        nodes[node_id] = {
            "id": node_id,
            "type": "entry_point",
            "label": cap_name,
            "raw_id": cap_name,
            "file_count": len(files),
            "files": files,
            "has_duplicate": len(files) > 1,
        }
        if len(files) > 1:
            nodes[node_id]["_issue"] = "duplicate_entry_point"
            nodes[node_id]["_issue_detail"] = (
                f"'{cap_name}' has {len(files)} routes: {', '.join(files)}"
            )
