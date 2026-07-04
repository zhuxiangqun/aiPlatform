"""RunContext builder — auto-populate from GraphIndex entity traversal.

Phase 10.2: scans user questions for known entity names, traverses GraphIndex
neighbors, and builds a partial RunContext dict. Caller-provided context can
then be merged using ``merge_run_context()`` with priority rules.

Moved from materials_chat.py Phase 1 refactoring.
"""

from __future__ import annotations

from typing import Dict, List, Optional


def build_run_context_from_graph(question: str, domain_id: str) -> Optional[dict]:
    """Scan question for entity names → GraphIndex traversal → partial RunContext.

    Populates entity/entity_type/situation from graph topology.
    Dynamic fields (priority, realtime constraints) remain empty —
    Phase 10.3 fills them from DataSource APIs.
    """
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex, GraphNode

        graph = GraphIndex.load(domain_id)
        if not graph or not graph._nodes:
            return None

        candidates: List[GraphNode] = []
        q_lower = question.lower()
        for node in graph._nodes.values():
            name_lower = node.entity_name.lower()
            if len(name_lower) >= 2 and name_lower in q_lower:
                candidates.append(node)

        if not candidates:
            return None

        candidates.sort(key=lambda n: len(n.entity_name), reverse=True)
        entity = candidates[0]

        neighbors = graph.get_neighbors(entity.entity_id, direction="both")
        neighbor_summary: List[str] = []
        for nb in neighbors[:5]:
            neighbor_summary.append(f"{nb.class_name}:{nb.entity_name}")

        ctx: dict = {
            "entity": entity.entity_name,
            "entity_type": entity.class_name,
            "situation": "",
            "priority": "",
            "constraints": [],
        }
        if neighbor_summary:
            ctx["situation"] = f"关联实体: {', '.join(neighbor_summary)}"

        return ctx
    except Exception:
        return None


def merge_run_context(caller_ctx: Optional[dict], graph_ctx: Optional[dict]) -> Optional[dict]:
    """Merge caller-provided and graph-derived RunContext with priority rules.

    Priority:
        entity/entity_type → caller wins if provided, else graph
        situation         → caller wins (real-time > static)
        priority          → caller wins (business context > topology)
        constraints       → merged (graph first, caller appended, deduplicated)

    Returns merged dict or None if both are None.
    """
    if not caller_ctx and not graph_ctx:
        return None
    if caller_ctx and not graph_ctx:
        return dict(caller_ctx)
    if graph_ctx and not caller_ctx:
        return dict(graph_ctx)

    merged = dict(graph_ctx)
    if caller_ctx.get("entity"):
        merged["entity"] = caller_ctx["entity"]
    if caller_ctx.get("entity_type"):
        merged["entity_type"] = caller_ctx["entity_type"]
    if caller_ctx.get("situation"):
        merged["situation"] = caller_ctx["situation"]
    if caller_ctx.get("priority"):
        merged["priority"] = caller_ctx["priority"]

    caller_constraints = list(caller_ctx.get("constraints") or [])
    graph_constraints = list(graph_ctx.get("constraints") or [])
    seen = set(graph_constraints)
    merged["constraints"] = graph_constraints + [c for c in caller_constraints if c not in seen]

    return merged
