"""
sys_code_intel — Code intelligence tools for Agents.

Provides pre-built dependency graph queries via SQLite index.
Replaces grep/glob/read exploration loops with single indexed queries.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _load_graph():
    """Lazy-load the code graph (nodes + edges) from SQLite or in-memory."""
    from core.harness.knowledge.code_graph import repo_root, default_roots, build_graph
    _repo_root = repo_root()
    roots = default_roots()
    abs_roots = [(_repo_root / r).resolve() for r in roots]
    return build_graph(_repo_root, abs_roots)


def _ensure_graph():
    """Get cached nodes + edges. Returns (nodes, edges)."""
    nodes, edg, _ = _load_graph()
    return nodes, edg


def _resolve_file(query: str, nodes: Dict) -> Optional[str]:
    """Resolve a query to a specific file path in the graph.
    Handles: full paths, basenames, symbol names prefixed with file."""
    if query in nodes:
        return query
    # Try basename match
    matches = [n for n in nodes if n.endswith("/" + query) or n.endswith(query)]
    if len(matches) == 1:
        return matches[0]
    # Try symbol match: find which file contains this symbol
    for nid, n in nodes.items():
        for sym in n.get("symbols", []):
            if sym[0] == query or query in str(sym[0]):
                return nid
    # Fallback: partial path match
    partial = [n for n in nodes if query in n]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1 and len(partial) <= 5:
        return partial[0]  # best guess
    return None


def sys_code_intel_context(task: str, *, roots: List[str] = None) -> Dict[str, Any]:
    u"""Return context-relevant code graph data for a given development task.

    Uses the pre-built code dependency graph (core/harness/knowledge/code_graph.py)
    to answer "where should I start" without spawning Explore sub-agents.

    Returns: {task, stats, health, related: [{file, imports}]}
    """
    from core.harness.knowledge.code_graph import build_context
    return build_context(task, roots)


def sys_code_intel_blast(file_path: str) -> List[str]:
    u"""Return the forward blast radius of a file (all files reachable via imports)."""
    nodes, _ = _ensure_graph()
    from core.harness.knowledge.code_graph import blast
    file_path = _resolve_file(file_path, nodes) or file_path
    if file_path not in nodes:
        return []
    return blast(dict(nodes), file_path)


def sys_code_intel_callers(target: str, *, max_results: int = 50) -> Dict[str, Any]:
    u"""Return all files that depend on (import from) the given file or symbol.

    Args:
        target: File path or symbol name (e.g., 'core/harness/execution/loop.py' or 'ReActLoop')
        max_results: Maximum number of results to return

    Returns:
        {target, count, callers: [{file, dep_count, symbols}]}
    """
    nodes, edges = _ensure_graph()
    resolved = _resolve_file(target, nodes)
    if not resolved:
        return {"target": target, "count": 0, "callers": [], "note": "File/symbol not found in code graph"}

    callers = []
    for nid, n in nodes.items():
        if nid == resolved:
            continue
        out_list = n.get("out", [])
        if isinstance(out_list, list) and resolved in out_list:
            callers.append({
                "file": nid,
                "kind": "import",
                "dep_count": len(out_list) if isinstance(out_list, list) else 0,
                "symbols": [s[0] for s in n.get("symbols", [])[:10]],
            })

    # Also include cross-language API callers from edges
    for edge in edges:
        if edge.get("to") == resolved and edge.get("kind") == "api":
            caller_file = edge.get("from", "")
            if caller_file and caller_file != resolved:
                # Avoid duplicates
                if not any(c["file"] == caller_file for c in callers):
                    callers.append({
                        "file": caller_file,
                        "kind": "api",
                        "label": edge.get("label", ""),
                        "dep_count": 0,
                        "symbols": [],
                    })

    callers.sort(key=lambda x: -x["dep_count"])
    total = len(callers)
    if total > max_results:
        callers = callers[:max_results]

    return {"target": resolved, "count": total, "callers": callers}


def sys_code_intel_callees(target: str, *, max_results: int = 50) -> Dict[str, Any]:
    u"""Return all files that the given file/symbol depends on (imports).

    Args:
        target: File path or symbol name
        max_results: Maximum number of results to return

    Returns:
        {target, count, callees: [{file, symbols}]}
    """
    nodes, edges = _ensure_graph()
    resolved = _resolve_file(target, nodes)
    if not resolved or resolved not in nodes:
        return {"target": target, "count": 0, "callees": [], "note": "File/symbol not found in code graph"}

    node = nodes[resolved]
    out_list = node.get("out", [])
    callees = []
    for f in (out_list if isinstance(out_list, list) else []):
        callee_node = nodes.get(f, {})
        callees.append({
            "file": f,
            "kind": "import",
            "symbols": [s[0] for s in callee_node.get("symbols", [])[:10]],
        })

    # Also include cross-language API callees (frontend API calls from this file)
    for edge in edges:
        if edge.get("from") == resolved and edge.get("kind") == "api":
            callee_file = edge.get("to", "")
            if callee_file:
                callees.append({
                    "file": callee_file,
                    "kind": "api",
                    "label": edge.get("label", ""),
                    "symbols": [],
                })

    total = len(callees)
    if total > max_results:
        callees = callees[:max_results]

    return {"target": resolved, "count": total, "callees": callees}


def sys_code_intel_affected(file_path: str, *, max_results: int = 100) -> Dict[str, Any]:
    u"""Return all files in the blast radius of a given file, with dependency depth.

    Returns files that could be affected by a change to this file,
    ordered by dependency distance (closest first).

    Args:
        file_path: Path to the file to analyze
        max_results: Maximum number of results

    Returns:
        {target, depth, affected: [{file, depth, reason}]}
    """
    nodes, _ = _ensure_graph()
    resolved = _resolve_file(file_path, nodes)
    if not resolved or resolved not in nodes:
        return {"target": file_path, "depth": 0, "affected": [], "note": "File not found in code graph"}

    # BFS from the target, tracking depth
    visited = {resolved: 0}
    queue = [resolved]
    while queue:
        current = queue.pop(0)
        current_depth = visited[current]
        if current_depth > 10:
            continue
        for nid, n in nodes.items():
            if nid in visited:
                continue
            out_list = n.get("out", [])
            if isinstance(out_list, list) and current in out_list:
                depth = current_depth + 1
                visited[nid] = depth
                queue.append(nid)

    affected = []
    for f, d in sorted(visited.items(), key=lambda x: x[1]):
        if f == resolved:
            continue
        affected.append({"file": f, "depth": d})

    if len(affected) > max_results:
        affected = affected[:max_results]

    return {"target": resolved, "depth": max(visited.values()) if visited else 0, "affected": affected, "total": len(affected)}


def sys_code_intel_search(query: str, *, kind: str = "all", max_results: int = 30) -> Dict[str, Any]:
    u"""Search the code graph for files and symbols matching a query.

    Args:
        query: Search term (file path fragment, symbol name, or class name)
        kind: 'file' | 'symbol' | 'all' (default: all)
        max_results: Maximum number of results

    Returns:
        {query, results: [{file, kind, match}]}
    """
    nodes, _ = _ensure_graph()
    q = query.lower()
    results = []

    if kind in ("all", "file"):
        for nid in nodes:
            if q in nid.lower():
                results.append({"file": nid, "kind": "file", "match": nid})

    if kind in ("all", "symbol"):
        for nid, n in nodes.items():
            for sym in n.get("symbols", []):
                if len(sym) >= 1 and q in str(sym[0]).lower():
                    results.append({"file": nid, "kind": "symbol", "match": f"{sym[1]}:{sym[0]} (line {sym[2] if len(sym) > 2 else '?'})"})

    results.sort(key=lambda x: x["file"])
    if len(results) > max_results:
        results = results[:max_results]

    return {"query": query, "count": len(results), "results": results}


def sys_code_intel_subclasses(parent: str, *, max_results: int = 50) -> Dict[str, Any]:
    u"""Find all subclasses of a given parent class in the codebase.

    Uses the parent field in symbol data (4th element) to find is-a relationships.
    Returns subclass names and their file locations.

    Args:
        parent: Parent class name to search for subclasses
        max_results: Maximum number of results

    Returns:
        {parent, count, subclasses: [{name, file, line}]}
    """
    nodes, _ = _ensure_graph()
    subclasses = []
    for nid, nd in nodes.items():
        for sym in nd.get("symbols", []):
            if isinstance(sym, (list, tuple)) and len(sym) >= 4:
                name = sym[0]
                kind = sym[1]
                line = sym[2]
                sym_parent = sym[3]
                if sym_parent == parent and kind == "class":
                    subclasses.append({
                        "name": name,
                        "file": nid,
                        "line": line,
                    })

    total = len(subclasses)
    if total > max_results:
        subclasses = subclasses[:max_results]

    return {"parent": parent, "count": total, "subclasses": subclasses}
