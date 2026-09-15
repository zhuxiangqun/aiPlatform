"""
sys_graph_validate — online consistency validation for domain GraphIndex.

Business authority: domain YAML + GraphIndex via ontology_validator.validate_domain.
Wiki KnowledgeValidator axioms are a separate knowledge-base track — not used here.

Contract (ONTOLOGY_RUNTIME_AUTHORITY §6):
  Unchecked / failed-to-run → status=unchecked|error, valid MUST NOT be true.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("aiplat.syscalls.graph_validate")


def _item_to_violation(item: Any) -> Dict[str, Any]:
    return {
        "rule": getattr(item, "item_type", None) or getattr(item, "axiom_id", "unknown"),
        "entity": getattr(item, "entity_name", "") or "",
        "class_name": getattr(item, "class_name", "") or "",
        "detail": getattr(item, "message", None) or getattr(item, "description", "") or str(item),
        "severity": getattr(item, "severity", "warning"),
    }


def _finalize(
    *,
    operation: str,
    violations: List[Dict[str, Any]],
    suggestions: List[Dict[str, Any]],
    checks_run: List[str],
    skipped_checks: List[Dict[str, str]],
    ingest_triggered: int = 0,
    status_hint: str = "",
    error: str = "",
) -> Dict[str, Any]:
    """Apply false-pass ban: no checks_run ⇒ unchecked + valid=false."""
    if error and not checks_run:
        status = "error"
        valid = False
    elif not checks_run:
        status = "unchecked"
        valid = False
    elif skipped_checks:
        status = status_hint or "degraded"
        # Only trust checks that actually ran
        valid = len(violations) == 0 and status != "unchecked"
    else:
        status = status_hint or "ok"
        valid = len(violations) == 0

    # Hard rule: unchecked/error without successful checks never reports valid=true
    if status in ("unchecked", "error") and not checks_run:
        valid = False

    health_score = max(0, 100 - len(violations) * 5 - len(suggestions) * 2)
    if status == "unchecked":
        health_score = 0

    out: Dict[str, Any] = {
        "valid": valid,
        "violations": violations[:20],
        "suggestions": suggestions[:10],
        "health_score": min(100, health_score),
        "operation": operation,
        "status": status,
        "checks_run": list(checks_run),
        "skipped_checks": list(skipped_checks),
        "ingest_triggered": ingest_triggered,
    }
    if error:
        out["error"] = error
    return out


async def sys_graph_validate(
    domain_id: str,
    *,
    operation: str = "consistency",
    target_entity: str = "",
) -> Dict[str, Any]:
    """Validate graph consistency for a ReconSubgraph or persistent domain.

    Args:
        domain_id: Graph domain to validate (e.g., "_recon_abc" or "supply-chain")
        operation: "consistency" | "contradiction" | "completeness"
        target_entity: Optional entity_id to scope validation to a single node

    Returns:
        {valid, violations, suggestions, health_score, operation, status,
         checks_run, skipped_checks, ingest_triggered}
    """
    checks_run: List[str] = []
    skipped_checks: List[Dict[str, str]] = []
    violations: List[Dict[str, Any]] = []
    suggestions: List[Dict[str, Any]] = []

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
    except Exception as e:
        return _finalize(
            operation=operation,
            violations=[],
            suggestions=[],
            checks_run=[],
            skipped_checks=[],
            error=f"Cannot load {domain_id}: {e}",
        )

    if operation in ("consistency", "contradiction"):
        if target_entity:
            checks_run.append("scoped_entity_edges")
            node = graph.get_node(target_entity)
            if not node:
                violations.append({
                    "rule": "entity_not_found",
                    "entity": target_entity,
                    "detail": "Entity not found in graph",
                    "severity": "error",
                })
            else:
                for edge in node.out_edges + node.in_edges:
                    if edge.confidence < 0.5:
                        violations.append({
                            "rule": "low_confidence_edge",
                            "entity": target_entity,
                            "edge": f"{edge.source_id} → {edge.target_id} ({edge.relation_name})",
                            "detail": f"Confidence {edge.confidence:.2f} below threshold",
                            "severity": "warning",
                        })
        else:
            try:
                from core.harness.knowledge.ontology_validator import validate_domain
                report = validate_domain(domain_id)
                checks_run.append("domain_graph_vs_yaml")
                for item in report.items:
                    v = _item_to_violation(item)
                    violations.append(v)
                    if v.get("rule") == "orphan_node" or (
                        "source" in (v.get("detail") or "").lower()
                    ):
                        suggestions.append({
                            "action": "add_source_doc" if "source" in (v.get("detail") or "").lower()
                            else "fix_class_mapping",
                            "target": v.get("entity") or "",
                            "reason": v.get("detail") or "",
                        })
            except Exception as e:
                logger.warning("domain_graph_vs_yaml failed for %s: %s", domain_id, e)
                skipped_checks.append({
                    "check": "domain_graph_vs_yaml",
                    "reason": str(e),
                })

    if operation == "completeness":
        checks_run.append("completeness")
        stats = graph.stats()
        if stats.get("nodes", 0) > 0 and stats.get("edges", 0) == 0:
            suggestions.append({
                "action": "add_relations",
                "target": "all",
                "reason": f"Graph has {stats['nodes']} nodes but 0 edges — missing relations",
            })

    # Unknown operation → explicit unchecked (not silent ok)
    if operation not in ("consistency", "contradiction", "completeness"):
        skipped_checks.append({
            "check": operation,
            "reason": f"unsupported operation '{operation}'",
        })

    ingest_triggered = 0
    # Only auto-ingest when we actually ran checks and found actionable issues
    if checks_run and suggestions and violations:
        try:
            for s in suggestions:
                action = s.get("action", "")
                target = s.get("target", "")
                if not target or target == "all":
                    continue
                if action == "add_source_doc":
                    _enqueue_single_entity_refresh(target, "lint:missing_source")
                    ingest_triggered += 1
                elif action == "add_relations":
                    _enqueue_single_entity_refresh(target, "lint:missing_relations")
                    ingest_triggered += 1
                elif action == "low_confidence":
                    _enqueue_single_entity_refresh(target, "lint:low_confidence")
                    ingest_triggered += 1
        except Exception as e:
            logger.debug("Lint-to-Ingest loop failed (non-blocking): %s", e)

    return _finalize(
        operation=operation,
        violations=violations,
        suggestions=suggestions,
        checks_run=checks_run,
        skipped_checks=skipped_checks,
        ingest_triggered=ingest_triggered,
    )


def _enqueue_single_entity_refresh(entity_id: str, trigger: str) -> None:
    """Best-effort: enqueue an entity for incremental re-ingestion."""
    try:
        import logging as _log
        from core.harness.knowledge.wiki_engine import llm_curate_page, search_pages

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
        _log = __import__("logging").getLogger(__name__)
        _log.debug("Lint-to-Ingest: enqueue failed for entity '%s'", entity_id)
