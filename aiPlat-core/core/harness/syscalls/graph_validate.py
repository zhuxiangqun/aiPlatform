"""
sys_graph_validate — online consistency validation for graph edges/entities.

Wraps knowledge_validator's core validation capabilities (6 axiom validators)
for on-demand, per-entity or full-graph consistency checks.

Agent usage:
  sys_graph_validate(domain="_recon_abc", operation="consistency")
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("aiplat.syscalls.graph_validate")


async def sys_graph_validate(
    domain_id: str,
    *,
    operation: str = "consistency",
    target_entity: str = "",
) -> Dict[str, Any]:
    """Validate graph consistency for a ReconSubgraph or persistent domain.

    Args:
        domain_id: Graph domain to validate (e.g., "_recon_abc" or "supply-chain")
        operation: "consistency" → 6 axiom checks (A1/A3/A4/A5/A6/CARD_PARENT)
                   "contradiction" → detect contradictory edges
                   "completeness" → check for missing required relations
        target_entity: Optional entity_id to scope validation to a single node

    Returns:
        {valid, violations, suggestions, health_score, operation}
    """
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
    except Exception as e:
        return {"valid": False, "violations": [], "health_score": 0,
                "status": "error", "error": f"Cannot load {domain_id}: {e}"}

    violations: list = []
    suggestions: list = []

    if operation in ("consistency", "contradiction"):
        try:
            from core.harness.knowledge.knowledge_validator import KnowledgeValidator
            validator = KnowledgeValidator()

            if target_entity:
                # Scoped validation
                node = graph.get_node(target_entity)
                if not node:
                    violations.append({
                        "rule": "entity_not_found",
                        "entity": target_entity,
                        "detail": "Entity not found in graph",
                    })
                else:
                    # Check edges from/to this entity
                    for edge in node.out_edges + node.in_edges:
                        if edge.confidence < 0.5:
                            violations.append({
                                "rule": "low_confidence_edge",
                                "entity": target_entity,
                                "edge": f"{edge.source_id} → {edge.target_id} ({edge.relation_name})",
                                "detail": f"Confidence {edge.confidence:.2f} below threshold",
                            })
            else:
                # Full graph validation
                result = validator.validate(graph, domain_id=domain_id)
                violations = result.violations if hasattr(result, 'violations') else []

                for v in violations:
                    rule_id = getattr(v, 'rule_id', 'unknown')
                    if rule_id == "A5":
                        suggestions.append({
                            "action": "add_source_doc",
                            "target": getattr(v, 'entity_id', ''),
                            "reason": "Entity has no source document reference",
                        })

        except ImportError:
            logger.debug("KnowledgeValidator not available for online validation")
        except Exception as e:
            logger.debug("Validation failed: %s", e)

    # ── Completeness check ──
    if operation in ("completeness"):
        stats = graph.stats()
        if stats.get("nodes", 0) > 0 and stats.get("edges", 0) == 0:
            suggestions.append({
                "action": "add_relations",
                "target": "all",
                "reason": f"Graph has {stats['nodes']} nodes but 0 edges — missing relations",
            })

    health_score = max(0, 100 - len(violations) * 5 - len(suggestions) * 2)
    valid = len(violations) == 0

    # ── Lint-to-Ingest Feedback Loop ──
    # Automatically trigger re-ingestion for entities that validation found issues with.
    # This closes the loop: Lint findings → IngestQueue → incremental refresh.
    ingest_triggered = 0
    if suggestions and valid is False:
        try:
            for s in suggestions:
                action = s.get("action", "")
                target = s.get("target", "")
                if not target or target == "all":
                    continue

                if action == "add_source_doc" and target:
                    _enqueue_single_entity_refresh(target, "lint:missing_source")
                    ingest_triggered += 1

                elif action == "add_relations" and target:
                    _enqueue_single_entity_refresh(target, "lint:missing_relations")
                    ingest_triggered += 1

                elif action == "low_confidence" and target:
                    _enqueue_single_entity_refresh(target, "lint:low_confidence")
                    ingest_triggered += 1

        except Exception as e:
            logger.debug("Lint-to-Ingest loop failed (non-blocking): %s", e)

    return {
        "valid": valid,
        "violations": violations[:20],
        "suggestions": suggestions[:10],
        "health_score": min(100, health_score),
        "operation": operation,
        "status": "ok",
        "ingest_triggered": ingest_triggered,  # NEW: how many entities were auto-queued
    }


def _enqueue_single_entity_refresh(entity_id: str, trigger: str) -> None:
    """Best-effort: enqueue an entity for incremental re-ingestion.

    Calls llm_curate_page on any wiki pages that reference this entity.
    Non-blocking — failures are logged, not raised.
    """
    try:
        import logging as _log
        from core.harness.knowledge.wiki_engine import llm_curate_page, search_pages

        # Find wiki pages that reference this entity
        pages = search_pages(entity_id, limit=5)
        for page in pages:
            title = page.get("title", "")
            if title:
                try:
                    llm_curate_page(title, trigger=trigger)
                    _log.info("Lint-to-Ingest: queued refresh for '%s' (trigger=%s)", title, trigger)
                except Exception:
                    _log.debug("Lint-to-Ingest: refresh skipped for '%s'", title)
    except Exception:
        _log = __import__('logging').getLogger(__name__)
        _log.debug("Lint-to-Ingest: enqueue failed for entity '%s'", entity_id)
