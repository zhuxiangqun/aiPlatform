"""
sys_graph_query — Core syscall for querying the knowledge graph.

Lets Agent ask structural questions about the knowledge graph:
  - "How many nodes in domain X?"
  - "What classes exist in the ontology?"
  - "What are the relationships between A and B?"
  - "List all entities of class Y"
  - "Find shortest path from X to Y"

Routes to GraphIndex + GraphTraversal for Python-level graph operations.
Results are summarized for Agent consumption (max 800 chars per §5.26).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.syscall.graph")


async def sys_graph_query(
    query: str,
    *,
    domain_id: str = "default",
    operation: str = "auto",
    top_k: int = 10,
    max_chars: int = 800,
) -> Dict[str, Any]:
    """
    Query the knowledge graph for structural information.

    Args:
        query: Natural language query or entity/class name
        domain_id: Which knowledge domain to query (default: "default")
        operation: "auto" | "stats" | "classes" | "neighbors" | "path" | "search"
        top_k: Max results for list operations
        max_chars: Output truncation limit (§5.26)

    Returns:
        {
            "success": bool,
            "result": str,       # Human-readable answer
            "data": dict,        # Raw structured data
            "domain_id": str,
            "operation": str,
        }
    """
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        graph = GraphIndex.load(domain_id) if _graph_exists(domain_id) else GraphIndex(domain_id)
        if len(graph) == 0:
            return _result(False, f"Domain '{domain_id}' has no entities yet.", domain_id, operation)

        # ── Auto-detect operation from query ──
        if operation == "auto":
            operation = _detect_operation(query)

        if operation == "stats":
            return await _query_stats(graph, domain_id)
        elif operation == "classes":
            return await _query_classes(graph, domain_id, query)
        elif operation == "neighbors":
            return await _query_neighbors(graph, domain_id, query, top_k)
        elif operation == "path":
            return await _query_path(graph, domain_id, query)
        elif operation == "search":
            return await _query_search(graph, domain_id, query, top_k)
        else:
            return _result(False, f"Unknown operation: {operation}", domain_id, operation)

    except Exception as e:
        logger.warning("sys_graph_query failed: %s", e, exc_info=True)
        return _result(False, f"Graph query error: {str(e)[:200]}", domain_id, operation, error=str(e))


def _detect_operation(query: str) -> str:
    """Heuristic: infer the operation type from the query text."""
    q = query.lower()
    if any(kw in q for kw in ["多少", "几个", "how many", "count", "统计", "size", "节点数"]):
        return "stats"
    if any(kw in q for kw in ["类", "class", "类型", "type", "有哪些", "what are"]):
        return "classes"
    if any(kw in q for kw in ["关系", "关联", "连接", "related", "connected", "neighbor", "邻居", "相连"]):
        return "neighbors"
    if any(kw in q for kw in ["路径", "path", "route", "shortest", "最短"]):
        return "path"
    return "search"


# ── Operation handlers ──

async def _query_stats(graph, domain_id: str) -> Dict[str, Any]:
    s = graph.stats()
    nodes = s.get("node_count", 0)
    edges = s.get("edge_count", 0)
    avg_deg = s.get("avg_degree", 0)
    result_text = (
        f"Knowledge graph '{domain_id}' statistics:\n"
        f"  • Entities (nodes): {nodes}\n"
        f"  • Relationships (edges): {edges}\n"
        f"  • Average degree: {avg_deg}\n"
    )
    return _result(True, result_text, domain_id, "stats",
                   data={"nodes": nodes, "edges": edges, "avg_degree": avg_deg})


async def _query_classes(graph, domain_id: str, query: str) -> Dict[str, Any]:
    class_counts = {}
    for node in graph._nodes.values():
        cn = node.class_name or "unknown"
        class_counts[cn] = class_counts.get(cn, 0) + 1

    if not class_counts:
        return _result(True, f"No classes found in domain '{domain_id}'.", domain_id, "classes")

    lines = [f"Classes in '{domain_id}':"]
    for cn, count in sorted(class_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  • {cn}: {count} entities")
    return _result(True, "\n".join(lines)[:800], domain_id, "classes", data=class_counts)


async def _query_neighbors(graph, domain_id: str, query: str, top_k: int) -> Dict[str, Any]:
    entity_name = _extract_entity_name(query)
    node = graph.find_by_name(entity_name)
    if not node:
        candidates = []
        for n in graph._nodes.values():
            if entity_name.lower() in (n.entity_name or "").lower():
                candidates.append(n.entity_name)
        if candidates:
            return _result(True,
                f"Found {len(candidates)} matching entities: {', '.join(candidates[:10])}",
                domain_id, "neighbors", data={"matches": candidates[:10]})
        return _result(False, f"No entity named '{entity_name}' found.", domain_id, "neighbors")

    neighbors = graph.get_neighbors(node.entity_id)
    out_edges = getattr(node, "out_edges", []) or []
    in_edges = getattr(node, "in_edges", []) or []
    lines = [f"Entity: {node.entity_name} (class: {node.class_name})"]
    if out_edges:
        lines.append(f"  Relations outgoing ({len(out_edges)}):")
        for e in out_edges[:top_k]:
            target = graph.get_node(e.target_id)
            target_name = target.entity_name if target else e.target_id
            lines.append(f"    → {target_name} ({e.relation_name})")
    if in_edges:
        lines.append(f"  Relations incoming ({len(in_edges)}):")
        for e in in_edges[:top_k]:
            source = graph.get_node(e.source_id)
            source_name = source.entity_name if source else e.source_id
            lines.append(f"    ← {source_name} ({e.relation_name})")
    return _result(True, "\n".join(lines)[:800], domain_id, "neighbors")


async def _query_path(graph, domain_id: str, query: str) -> Dict[str, Any]:
    """Find path between two entities using BFS traversal."""
    from core.harness.ontology_engine.graph_traversal import traverse

    names = _extract_two_names(query)
    if len(names) < 2:
        return _result(False, "Could not identify two entities in query. Try: 'path from X to Y'", domain_id, "path")

    start_name, end_name = names[0], names[1]
    start = graph.find_by_name(start_name)
    end = graph.find_by_name(end_name)
    if not start:
        return _result(False, f"Start entity '{start_name}' not found.", domain_id, "path")
    if not end:
        return _result(False, f"End entity '{end_name}' not found.", domain_id, "path")

    # Use BFS traverse: check if end_id appears in result paths
    result = traverse(graph, start.entity_id, max_hops=3, direction="outgoing")
    paths = result.paths if hasattr(result, 'paths') else []
    
    # Filter paths that reach end_id
    reachable = [p for p in paths if end.entity_id in [s.entity_id for s in p.steps]]
    if not reachable:
        return _result(True,
            f"No path found between '{start_name}' and '{end_name}' within 3 hops.",
            domain_id, "path", data={"paths": []})

    lines = [f"Paths from '{start_name}' to '{end_name}' ({len(reachable)} found):"]
    for i, path in enumerate(reachable[:3]):
        hops = len(path.steps) - 1
        path_str = " → ".join(s.entity_name or s.entity_id for s in path.steps)
        lines.append(f"  Path {i+1} ({hops} hops): {path_str}")
    return _result(True, "\n".join(lines)[:800], domain_id, "path", data={"paths_count": len(reachable)})


async def _query_search(graph, domain_id: str, query: str, top_k: int) -> Dict[str, Any]:
    keyword = _extract_entity_name(query)
    matches = []
    for node in graph._nodes.values():
        if keyword.lower() in (node.entity_name or "").lower() or \
           keyword.lower() in (node.class_name or "").lower():
            matches.append({
                "entity": node.entity_name,
                "class": node.class_name,
                "id": node.entity_id,
            })

    if not matches:
        return _result(True, f"No entities matching '{keyword}' found.", domain_id, "search")

    lines = [f"Search results for '{keyword}' ({len(matches)} matches):"]
    for m in matches[:top_k]:
        lines.append(f"  • {m['entity']} ({m['class']})")
    return _result(True, "\n".join(lines)[:800], domain_id, "search", data=matches[:top_k])


# ── Helpers ──

def _result(success: bool, text: str, domain_id: str, operation: str,
            data: dict = None, error: str = None) -> Dict[str, Any]:
    return {
        "success": success,
        "result": text[:800],
        "data": data or {},
        "domain_id": domain_id,
        "operation": operation,
        "error": error,
    }


def _graph_exists(domain_id: str) -> bool:
    """Check if a persisted graph file exists for the domain."""
    import os as _os
    home = _os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat"))
    db_path = _os.path.join(home, "graph", f"{domain_id}.db")
    return _os.path.exists(db_path)


def _extract_entity_name(query: str) -> str:
    """Extract a likely entity name from NL query."""
    import re
    # Try quoted strings first
    m = re.search(r'["\"]([^"\"]+)["\"]', query)
    if m:
        return m.group(1)
    # Try "about X" or "called X" or "named X"
    for pat in [r'about\s+([A-Z][a-zA-Z_\s]+?)(?:\s|$)', r'from\s+([A-Z][a-zA-Z_\s]+?)(?:\s|to|$)',
                r'to\s+([A-Z][a-zA-Z_\s]+?)(?:\s|from|$)']:
        m = re.search(pat, query)
        if m:
            return m.group(1).strip()
    # Fallback: take the query as the name itself
    return query.strip()


def _extract_two_names(query: str) -> list:
    """Extract two entity names for path queries."""
    import re
    # Pattern: "from X to Y" or "between X and Y"
    m = re.search(r'from\s+([A-Za-z_\s]+?)\s+to\s+([A-Za-z_\s]+)', query)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    m = re.search(r'between\s+([A-Za-z_\s]+?)\s+and\s+([A-Za-z_\s]+)', query)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    # Fallback: split by "and", take last two capitalized words
    words = [w for w in query.split() if w[0].isupper()]
    return words[-2:] if len(words) >= 2 else []
