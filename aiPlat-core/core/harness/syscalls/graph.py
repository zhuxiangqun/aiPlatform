"""
Graph neighbor lookup syscall — thin wrapper over GraphIndex (v3.1).

Prevents agents from directly importing GraphIndex by providing
a shared syscall for entity neighbor traversal and recommendations.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ._trace import trace_syscall_entry

_log = logging.getLogger(__name__)


async def sys_graph_neighbors(
    entity_name: str,
    domain_id: str = "default",
    max_hops: int = 1,
    include_edges: bool = False,
) -> Dict[str, Any]:
    """Look up an entity in the graph and return its neighbors.

    Used by agents for proactive recommendations and context building.

    Returns:
      {entity: str, neighbors: [str], edges: [{source, target, relation}]}
    """
    trace_syscall_entry("sys_graph_neighbors")
    result: Dict[str, Any] = {"entity": entity_name, "neighbors": [], "edges": []}

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        node = graph.get_node(entity_name) or graph.find_by_name(entity_name)
        if not node:
            return result

        neighbors: set = set()
        for edge in (node.out_edges or []):
            n = graph.get_node(edge.target_id)
            if n:
                neighbors.add(n.entity_name)
            if include_edges:
                result["edges"].append({
                    "source": entity_name,
                    "target": n.entity_name if n else edge.target_id,
                    "relation": getattr(edge, "relation_label", "related_to"),
                })

        for edge in (node.in_edges or []):
            n = graph.get_node(edge.source_id)
            if n:
                neighbors.add(n.entity_name)
            if include_edges:
                result["edges"].append({
                    "source": n.entity_name if n else edge.source_id,
                    "target": entity_name,
                    "relation": getattr(edge, "relation_label", "related_to"),
                })

        result["neighbors"] = list(neighbors)[:max_hops * 10]
    except Exception:
        _log.debug("sys_graph_neighbors failed for %s in %s", entity_name, domain_id, exc_info=True)

    return result
