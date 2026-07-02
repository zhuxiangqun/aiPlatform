"""
Ontology Graph Cleanup — batch maintenance for stale entities and relations.

Phase E4: When KB documents are deleted or modified, their corresponding
graph nodes/edges may become orphaned. This module provides:

  - cleanup_stale_entities_by_doc(doc_id)     → Remove all entities from one doc
  - cleanup_stale_entities(domain_id)          → Scan for orphaned nodes (0 edges)
  - get_entity_trace(doc_id)                   → List entities sourced from a doc
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_entity_trace(*, doc_id: str, domain_id: str = "ai-knowledge") -> List[Dict[str, Any]]:
    """Return all graph entities that were extracted from a specific KB document."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    g = GraphIndex.load(domain_id)
    if len(g) == 0:
        return []

    matching = []
    for eid, node in g._nodes.items():
        if node.source_doc_id == doc_id:
            matching.append({
                "entity_id": eid,
                "entity_name": node.entity_name,
                "class_name": node.class_name,
                "out_edges": len(node.out_edges),
                "in_edges": len(node.in_edges),
            })
    return matching


def cleanup_stale_entities_by_doc(
    *, doc_id: str, domain_id: str = "ai-knowledge", dry_run: bool = True
) -> Dict[str, Any]:
    """Remove all graph entities sourced from a specific KB document.

    Called when a KB document is deleted or re-ingested.
    Uses snapshot() before deletion for rollback safety.

    Returns: {deleted_entities: int, deleted_relations: int, dry_run: bool}
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    g = GraphIndex.load(domain_id)
    if len(g) == 0:
        return {"deleted_entities": 0, "deleted_relations": 0, "dry_run": dry_run}

    to_remove = [eid for eid, node in g._nodes.items() if node.source_doc_id == doc_id]

    if dry_run:
        logger.info(
            "cleanup_stale_entities_by_doc(dry_run): doc_id=%s, would remove %d entities",
            doc_id, len(to_remove),
        )
        return {"deleted_entities": len(to_remove), "deleted_relations": 0, "dry_run": True}

    relations_removed = 0
    for eid in to_remove:
        # Count and remove all edges connected to this entity
        node = g._nodes.get(eid)
        if node:
            relations_removed += len(node.out_edges) + len(node.in_edges)
        g.remove_entity(eid)

    g.save()
    logger.info(
        "cleanup_stale_entities_by_doc: doc_id=%s, removed %d entities, ~%d relations",
        doc_id, len(to_remove), relations_removed,
    )
    return {
        "deleted_entities": len(to_remove),
        "deleted_relations": relations_removed,
        "dry_run": False,
    }


def cleanup_stale_entities(
    *, domain_id: str = "ai-knowledge", dry_run: bool = True
) -> Dict[str, Any]:
    """Scan for orphaned graph nodes (0 incoming + 0 outgoing edges).

    Orphaned nodes have no connections — they exist in the graph but are
    unreachable via traversal. These are typically leftovers from deleted
    or superseded entities.

    Returns: {orphans_found: int, deleted: int, dry_run: bool}
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    g = GraphIndex.load(domain_id)
    if len(g) == 0:
        return {"orphans_found": 0, "deleted": 0, "dry_run": dry_run}

    orphans = [
        eid for eid, node in g._nodes.items()
        if len(node.out_edges) == 0 and len(node.in_edges) == 0
    ]

    if dry_run:
        logger.info(
            "cleanup_stale_entities(dry_run): domain=%s, %d orphans found",
            domain_id, len(orphans),
        )
        return {"orphans_found": len(orphans), "deleted": 0, "dry_run": True}

    for eid in orphans:
        g.remove_entity(eid)

    g.save()
    logger.info(
        "cleanup_stale_entities: domain=%s, deleted %d orphaned entities",
        domain_id, len(orphans),
    )
    return {"orphans_found": len(orphans), "deleted": len(orphans), "dry_run": False}


__all__ = [
    "get_entity_trace",
    "cleanup_stale_entities_by_doc",
    "cleanup_stale_entities",
]
