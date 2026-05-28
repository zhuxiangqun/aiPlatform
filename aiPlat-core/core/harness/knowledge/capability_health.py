"""
Capability Health — analysis consumer of the capability graph.

Reads CapabilityGraphResult (pure nodes + edges) and produces:
  - Health score (0-100) with grade
  - Unused / orphan / unresolved detection
  - Top hubs by degree
  - Impact blast radius per node

Graph/Analysis separation: this module NEVER modifies the graph.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple


def capability_health_report(graph_result) -> Dict[str, Any]:
    """Produce a health report from a CapabilityGraphResult.

    Args:
        graph_result: CapabilityGraphResult from build_capability_graph()

    Returns:
        {
          score, grade, signals, issues, top_hubs, unused_skills,
          orphan_agents, unresolved_refs, by_type
        }
    """
    nodes = graph_result.nodes
    edges = graph_result.edges

    # Build adjacency
    out_degree: Dict[str, int] = defaultdict(int)
    in_degree: Dict[str, int] = defaultdict(int)
    neighbors: Dict[str, List[str]] = defaultdict(list)

    for e in edges:
        src, dst = e["from"], e["to"]
        out_degree[src] += 1
        in_degree[dst] += 1
        neighbors[src].append(dst)
        neighbors[dst].append(src)

    total_degree = {nid: out_degree.get(nid, 0) + in_degree.get(nid, 0) for nid in nodes}

    # Count by type
    by_type: Dict[str, int] = defaultdict(int)
    for n in nodes.values():
        by_type[n["type"]] += 1

    # ---- Issues detection ----

    # 1) Unused skills — skills with 0 in-degree (no agent references them)
    unused_skills: List[str] = []
    for nid, n in nodes.items():
        if n["type"] == "skill" and in_degree.get(nid, 0) == 0:
            unused_skills.append(n["label"])

    # 2) Orphan agents — agents with 0 out-degree (no skills/tools)
    orphan_agents: List[str] = []
    for nid, n in nodes.items():
        if n["type"] == "agent" and out_degree.get(nid, 0) == 0:
            orphan_agents.append(n["label"])

    # 3) Unresolved references — agent→skill edge where skill node is missing
    unresolved_refs: List[Dict[str, str]] = []
    for e in edges:
        if e["relation"] == "requires":
            if e["to"] not in nodes:
                unresolved_refs.append({"agent": e["from"], "target": e["to"], "target_type": nodes[e["from"]]["type"]})

    # 4) Entry point duplicates — same capability with multiple API routes
    entry_point_duplicates: List[Dict[str, Any]] = []
    for nid, n in nodes.items():
        if n.get("type") == "entry_point" and n.get("has_duplicate"):
            entry_point_duplicates.append({
                "capability": n["label"],
                "files": n.get("files", []),
                "detail": n.get("_issue_detail", ""),
            })

    # 5) Top hubs — nodes sorted by total degree
    top_hubs = sorted(
        [{"id": nid, "label": nodes[nid]["label"], "type": nodes[nid]["type"], "degree": total_degree[nid]}
         for nid in nodes],
        key=lambda x: x["degree"],
        reverse=True,
    )[:15]

    # ---- Health scoring ----

    total_agents = by_type.get("agent", 0)
    total_skills = by_type.get("skill", 0)
    total_tools = by_type.get("tool", 0)
    total_mcp = by_type.get("mcp_server", 0)
    total_nodes = len(nodes)
    total_edges = len(edges)
    used_skills = total_skills - len(unused_skills)

    score = 100.0

    # Penalty: unused skills (>30% → heavy penalty)
    if total_skills > 0:
        unused_ratio = len(unused_skills) / total_skills
        if unused_ratio > 0.5:
            score -= 20
        elif unused_ratio > 0.3:
            score -= 10
        elif unused_ratio > 0.1:
            score -= 5

    # Penalty: orphan agents
    if total_agents > 0:
        orphan_ratio = len(orphan_agents) / total_agents
        if orphan_ratio > 0.5:
            score -= 15
        elif orphan_ratio > 0.2:
            score -= 8
        elif orphan_ratio > 0:
            score -= 3

    # Penalty: unresolved references
    if unresolved_refs:
        score -= min(len(unresolved_refs) * 2, 20)

    # Penalty: entry point duplicates (same capability, multiple routes)
    if entry_point_duplicates:
        score -= min(len(entry_point_duplicates) * 3, 15)

    # Penalty: no tools (capability gap)
    if total_tools == 0:
        score -= 5

    # Penalty: no MCP servers
    if total_mcp == 0 and total_nodes > 0:
        score -= 2  # minor — MCP is optional

    # Bonus: high connectivity
    if total_nodes > 0:
        avg_degree = (2 * total_edges) / total_nodes
        if avg_degree >= 2.0:
            score = min(100, score + 5)
        elif avg_degree >= 1.0:
            score = min(100, score + 2)

    score = max(0, score)

    # Grade
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    # ---- Blast radius (impact analysis) ----
    top_blast = _compute_blast(nodes, out_degree, neighbors, top_n=10)

    return {
        "score": round(score, 1),
        "grade": grade,
        "signals": {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "agents": total_agents,
            "skills": total_skills,
            "used_skills": used_skills,
            "tools": total_tools,
            "mcp_servers": total_mcp,
            "avg_degree": round((2 * total_edges) / total_nodes, 2) if total_nodes > 0 else 0,
        },
        "issues": {
            "unused_skills": unused_skills,
            "orphan_agents": orphan_agents,
            "unresolved_refs": unresolved_refs,
            "entry_point_duplicates": entry_point_duplicates,
        },
        "top_hubs": top_hubs,
        "top_blast": top_blast,
        "by_type": dict(by_type),
    }


def _compute_blast(
    nodes: Dict[str, Dict[str, Any]],
    out_degree: Dict[str, int],
    neighbors: Dict[str, List[str]],
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """BFS blast radius: how many nodes are reachable from each node (forward only)."""
    results: List[Dict[str, Any]] = []

    for nid in nodes:
        visited: Set[str] = set()
        queue = [nid]
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            for nb in neighbors.get(cur, []):
                if nb not in visited:
                    queue.append(nb)
        blast = len(visited) - 1  # exclude self
        if blast > 0:
            results.append({"id": nid, "label": nodes[nid]["label"], "type": nodes[nid]["type"], "blast": blast})

    results.sort(key=lambda x: x["blast"], reverse=True)
    return results[:top_n]
