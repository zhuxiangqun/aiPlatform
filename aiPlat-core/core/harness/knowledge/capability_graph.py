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
            elif stale_ids:
                 pass  # incremental path handled above, shouldn't reach here
            else:
                # 0 stale — but check for NEW files on disk not in cache
                cache_ids = set(nodes.keys())
                # Quick scan: count expected nodes per type
                new_detected = False
                for dtype, prefix, subdir in [("agent", "agent:", "agents"), ("skill", "skill:", "skills")]:
                    engine_dir = _find_engine_dir(subdir)
                    if engine_dir and engine_dir.exists():
                        for d in engine_dir.iterdir():
                            if d.is_dir() and (d / ("AGENT.md" if dtype == "agent" else "SKILL.md")).exists():
                                if f"{prefix}{d.name}" not in cache_ids:
                                    new_detected = True
                                    break
                    # workspace
                    import os as _os2
                    ws = Path(_os2.getenv("AIPLAT_HOME", _os2.path.expanduser("~/.aiplat"))) / subdir
                    if ws.exists():
                        for d in ws.iterdir():
                            if d.is_dir() and (d / ("AGENT.md" if dtype == "agent" else "SKILL.md")).exists():
                                if f"workspace_{prefix}{d.name}" not in cache_ids:
                                    new_detected = True
                                    break
                    if new_detected:
                        break
                
                if new_detected:
                    pass  # fall through to full rebuild
                else:
                    # Still 0 stale + 0 new: compute degrees and return
                    _finalize(nodes, edges)
                    _resolve_cross_namespace_edges(nodes, edges)
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
    _resolve_cross_namespace_edges(nodes, edges)
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


def _infer_domain(category: str, tags: list) -> str:
    """Infer business domain from AGENT/SKILL category and tags."""
    cat = (category or "").lower()
    tag_set = set((t or "").lower() for t in (tags or []))
    if "engineering" in cat or "development" in cat or "engineering" in tag_set:
        return "研发工程"
    if "product" in cat or "pm" in tag_set:
        return "产品管理"
    if "quality" in cat or "qa" in cat or "testing" in tag_set:
        return "质量保证"
    if "design" in cat or "architecture" in tag_set:
        return "架构设计"
    if "management" in cat or "monitoring" in tag_set:
        return "治理管理"
    if "sales" in cat or "support" in cat:
        return "业务运营"
    return "通用能力"


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


def _resolve_cross_namespace_edges(nodes: dict, edges: list):
    """Resolve workspace_skill: → skill: cross-namespace references.

    Workspace agents can use engine skills, but the edge builder creates
    workspace_skill: edges. This function fixes unresolved edges by falling
    back to the engine namespace.
    """
    node_ids = set(nodes.keys())
    fixed = 0
    namespace_fallbacks = [
        ("workspace_skill:", "skill:"),
        ("workspace_agent:", "agent:"),
    ]
    for e in edges:
        target = e.get("to", "")
        if target in node_ids:
            continue
        for ws_prefix, eng_prefix in namespace_fallbacks:
            if target.startswith(ws_prefix):
                eng_target = eng_prefix + target[len(ws_prefix):]
                if eng_target in node_ids:
                    e["to"] = eng_target
                    fixed += 1
                    break
    return fixed


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

def _scan_agents_dir(agents_root: Path, *, node_prefix: str, nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan an agents root directory for AGENT.md files and populate nodes/edges.

    Uses rglob to recursively find AGENT.md files (catches nested imports).
    Workspace agents reference workspace_skill: namespace, not skill:.
    """
    if not agents_root or not agents_root.exists():
        return
    seen_dirs: set = set()
    # Determine skill namespace based on agent scope
    skill_prefix = "workspace_skill" if node_prefix == "workspace_agent" else "skill"
    for md_file in sorted(agents_root.rglob("AGENT.md")):
        # Skip .revisions and __pycache__ directories
        if ".revisions" in md_file.parts or "__pycache__" in md_file.parts:
            continue
        agent_dir = md_file.parent
        if str(agent_dir.resolve()) in seen_dirs:
            continue
        seen_dirs.add(str(agent_dir.resolve()))
        agent_id = agent_dir.name
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        fm = _parse_frontmatter(text)

        # Detect nesting
        depth = len(agent_dir.relative_to(agents_root).parts)
        is_nested = depth > 1

        node_id = f"{node_prefix}:{agent_id}" if node_prefix else f"agent:{agent_id}"
        nodes[node_id] = {
            "id": node_id,
            "type": "agent",
            "label": fm.get("name", agent_id),
            "raw_id": agent_id,
            "agent_type": fm.get("agent_type", fm.get("type", "")),
            "status": fm.get("status", "unknown"),
            "category": fm.get("category", ""),
            "tags": fm.get("tags", []),
            "domain": _infer_domain(fm.get("category", ""), fm.get("tags", [])),
            "path": str(agent_dir),
            "nested": is_nested,
            "nesting_depth": depth,
        }

        if is_nested:
            nodes[node_id]["_issues"] = nodes[node_id].get("_issues", []) + [{
                "code": "nested_agent_dir",
                "level": "error",
                "message": f"Agent at depth {depth} under agents root — likely broken zip import. Move to {agents_root}/{agent_id}/",
            }]

        # agent → skill edges (accept required_skills OR skills field)
        # Use skill_prefix for correct namespace (workspace agents → workspace_skill:)
        skill_refs = fm.get("required_skills") or fm.get("skills") or []
        if isinstance(skill_refs, str):
            skill_refs = [skill_refs]
        for skill_ref in skill_refs:
            edges.append({"from": node_id, "to": f"{skill_prefix}:{skill_ref}", "relation": "requires"})

        # agent → tool edges
        tool_refs = fm.get("required_tools") or fm.get("tools") or []
        if isinstance(tool_refs, str):
            tool_refs = [tool_refs]
        for tool_ref in tool_refs:
            edges.append({"from": node_id, "to": f"tool:{tool_ref}", "relation": "requires"})

        # system_prompt presence
        if not fm.get("system_prompt"):
            nodes[node_id]["_issues"] = nodes[node_id].get("_issues", []) + [{
                "code": "missing_system_prompt",
                "level": "warning",
                "message": "Missing system_prompt — runtime will use CLAUDE.md as fallback",
            }]


def _scan_agents(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan engine and workspace agents directories."""
    # Engine agents (core/engine/agents/)
    engine_root = _find_engine_dir("agents")
    _scan_agents_dir(engine_root, node_prefix="agent", nodes=nodes, edges=edges)

    # Workspace agents (~/.aiplat/agents/)
    import os as _os
    aiplat_home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    workspace_root = Path(aiplat_home) / "agents"
    _scan_agents_dir(workspace_root, node_prefix="workspace_agent", nodes=nodes, edges=edges)


def _scan_skills_dir(skills_root: Path, *, node_prefix: str, nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan a skills root directory for SKILL.md files and populate nodes/edges.

    Uses rglob to recursively find SKILL.md files (catches nested imports).
    Reports nesting as warnings via node metadata.
    """
    if not skills_root or not skills_root.exists():
        return
    seen_dirs: set = set()
    for md_file in sorted(skills_root.rglob("SKILL.md")):
        # Skip .revisions and __pycache__ directories
        if ".revisions" in md_file.parts or "__pycache__" in md_file.parts:
            continue
        skill_dir = md_file.parent
        if str(skill_dir.resolve()) in seen_dirs:
            continue
        seen_dirs.add(str(skill_dir.resolve()))
        skill_id = skill_dir.name
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        fm = _parse_frontmatter(text)
        body = text.split("---", 2)[2] if text.count("---") >= 2 else text

        deps = _extract_syscalls_from_sop(body)

        # Detect nesting: if skill_dir is not a direct child of skills_root
        depth = len(skill_dir.relative_to(skills_root).parts)
        is_nested = depth > 1

        node_id = f"{node_prefix}:{skill_id}" if node_prefix else f"skill:{skill_id}"
        nodes[node_id] = {
            "id": node_id,
            "type": "skill",
            "label": fm.get("name", skill_id),
            "raw_id": skill_id,
            "category": fm.get("category", ""),
            "status": fm.get("status", "unknown"),
            "effects": fm.get("effects", []),
            "syscalls_used": deps,
            "path": str(skill_dir),
            "nested": is_nested,
            "nesting_depth": depth,
        }

        # Mark nested skills with a warning issue
        if is_nested:
            nodes[node_id]["_issues"] = nodes[node_id].get("_issues", []) + [{
                "code": "nested_skill_dir",
                "level": "error",
                "message": f"Skill at depth {depth} under skills root — likely broken zip import. Move to {skills_root}/{skill_id}/",
            }]

        # syscall → skill edges
        for syscall_name in deps:
            edges.append({"from": node_id, "to": f"syscall:{syscall_name}", "relation": "uses"})

        # skill → tool edges (from frontmatter tools: field — NEW)
        tool_refs = fm.get("tools") or []
        if isinstance(tool_refs, str):
            tool_refs = [t.strip() for t in tool_refs.split(",") if t.strip()]
        for tool_ref in tool_refs:
            if isinstance(tool_ref, str) and tool_ref.strip():
                edges.append({"from": node_id, "to": f"tool:{tool_ref.strip()}", "relation": "requires"})

        # skill → model edge (if model field is declared)
        model = fm.get("model")
        if isinstance(model, str) and model.strip():
            edges.append({"from": node_id, "to": f"model:{model.strip()}", "relation": "requires"})

        # execution_type visibility
        exec_type = fm.get("execution_type", "")
        if exec_type:
            nodes[node_id]["execution_type"] = str(exec_type)

        # handler.py presence check
        handler_path = skill_dir / "handler.py"
        if handler_path.exists():
            nodes[node_id]["has_handler"] = True
        if exec_type == "handler" and not handler_path.exists():
            nodes[node_id]["_issues"] = nodes[node_id].get("_issues", []) + [{
                "code": "handler_missing",
                "level": "error",
                "message": f"execution_type=handler but handler.py not found",
            }]
        if handler_path.exists() and exec_type != "handler":
            nodes[node_id]["_issues"] = nodes[node_id].get("_issues", []) + [{
                "code": "handler_unused",
                "level": "warning",
                "message": f"handler.py exists but execution_type is '{exec_type}' (not 'handler')",
            }]


def _scan_skills(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan engine and workspace skills directories."""
    # Engine skills (core/engine/skills/)
    engine_root = _find_engine_dir("skills")
    _scan_skills_dir(engine_root, node_prefix="skill", nodes=nodes, edges=edges)

    # Workspace skills (~/.aiplat/skills/)
    import os as _os
    aiplat_home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    workspace_root = Path(aiplat_home) / "skills"
    _scan_skills_dir(workspace_root, node_prefix="workspace_skill", nodes=nodes, edges=edges)


def _scan_tools(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    """Scan ToolRegistry for registered tools, with disk-based fallbacks."""
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

        # Fallback 1: syscall functions from harness
        try:
            from core.harness.syscalls import __all__ as _syscall_all
            for func_name in _syscall_all:
                tgt = f"tool:{func_name}"
                if tgt not in nodes and func_name.startswith("sys_"):
                    nodes[tgt] = {
                        "id": tgt,
                        "type": "syscall",
                        "label": func_name,
                        "raw_id": func_name,
                        "description": f"Syscall: {func_name}",
                        "category": "syscall",
                    }
        except Exception:
            pass

        # Fallback 2: discover tools from source files (in case runtime registry is empty)
        if len(tool_names) == 0:
            _scan_tool_source_files(nodes)

    except Exception:
        # Cold start: ToolRegistry unavailable, use file-based discovery
        _scan_tool_source_files(nodes)


def _scan_tool_source_files(nodes: Dict[str, Dict[str, Any]]):
    """Discover tools by scanning tool source files (cold-start fallback)."""
    import ast as _ast
    import os as _os

    search_dirs = [
        Path(__file__).parent.parent.parent / "apps" / "tools",  # engine tools
        Path(_os.path.expanduser("~/.aiplat/tools")),  # workspace tools
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                tree = _ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
                for node in _ast.walk(tree):
                    # Pattern: class Foo(BaseTool) with name="xxx" in config
                    if isinstance(node, _ast.ClassDef):
                        for base in getattr(node, 'bases', []):
                            base_name = getattr(base, 'id', '') if isinstance(base, _ast.Name) else ''
                            if base_name in ("BaseTool", "Tool"):
                                _extract_tool_name_from_class(nodes, node, py_file)
                    # Pattern: TOOL_DEF = {"name": "xxx", ...}
                    if isinstance(node, _ast.Assign):
                        for target in getattr(node, 'targets', []):
                            if isinstance(target, _ast.Name) and target.id == "TOOL_DEF":
                                _extract_tool_name_from_dict(nodes, node, py_file)
            except Exception:
                continue


def _extract_tool_name_from_class(nodes: dict, cls_node, py_file: Path):
    """Extract tool name from ToolConfig in class definition."""
    import ast as _ast
    for item in _ast.walk(cls_node):
        if isinstance(item, _ast.Call) and isinstance(getattr(item, 'func', None), _ast.Name):
            if item.func.id in ("ToolConfig",):
                for kw in getattr(item, 'keywords', []):
                    if kw.arg == "name" and isinstance(kw.value, _ast.Constant):
                        name = kw.value.value
                        if name not in nodes:
                            nodes[f"tool:{name}"] = {
                                "id": f"tool:{name}",
                                "type": "tool",
                                "label": name,
                                "raw_id": name,
                                "description": "",
                                "category": "",
                            }
                        return


def _extract_tool_name_from_dict(nodes: dict, assign_node, py_file: Path):
    """Extract tool name from TOOL_DEF dict."""
    import ast as _ast
    if isinstance(assign_node.value, _ast.Dict):
        for k, v in zip(getattr(assign_node.value, 'keys', []) or [], getattr(assign_node.value, 'values', []) or []):
            if isinstance(k, _ast.Constant) and k.value == "name" and isinstance(v, _ast.Constant):
                name = v.value
                if f"tool:{name}" not in nodes:
                    nodes[f"tool:{name}"] = {
                        "id": f"tool:{name}",
                        "type": "tool",
                        "label": name,
                        "raw_id": name,
                        "description": "",
                        "category": "",
                    }
                return


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
        "prompt.injection": _re.compile(r'@router\.\w+\([\"\']prompt[\w/]*inject'),
    }

    found: Dict[str, List[str]] = {}
    for py_file in sorted(routers_dir.glob("*.py")):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for cap_name, pattern in capability_patterns.items():
            if pattern.search(content):
                # workspace_agents.py provides workspace-scoped agent creation — not a duplicate
                if cap_name == "agent.create" and py_file.name == "workspace_agents.py":
                    continue
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
