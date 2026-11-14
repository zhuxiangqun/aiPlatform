"""
Health & Quality API (Phase 4 — pipeline feedback loop).

Endpoints for ontology health checks, composite health scoring,
and per-entity quality signal tracking.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel

router = APIRouter(tags=["wiki-health-quality"])


@router.get("/health/triggers", response_model=Dict[str, Any])
async def get_health_triggers(collection: str = "default"):
    """Get triggered curation tasks from ontology health checks.

    Args:
        collection: collection 参数。
    """
    from core.harness.knowledge.knowledge_quality import check_ontology_health_triggers
    triggers = check_ontology_health_triggers(collection_id=collection)
    return {"triggers": triggers, "total": len(triggers), "collection_id": collection}


@router.get("/health/score", response_model=Dict[str, Any])
async def get_ontology_health_score(collection: str = "default"):
    """Get composite ontology health score from axiom validation + quality signals.

    Args:
        collection: collection 参数。
    """
    try:
        from core.harness.knowledge.knowledge_validator import validate_all
        report = validate_all(collection_id=collection)
        return {
            "axiom_score": report.score,
            "violations": report.violations_by_severity,
            "passed_axioms": len(report.passed_axioms),
            "failed_axioms": len(report.failed_axioms),
            "total_triples": report.total_triples,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/{entity_uri:path}", response_model=Dict[str, Any])
async def get_entity_quality(entity_uri: str, collection: str = "default"):
    """Get quality score and signal history for an ontology entity.

    Args:
        entity_uri: entity_uri 参数。
        collection: collection 参数。
    """
    from core.harness.knowledge.knowledge_quality import get_entity_quality_score  # P0-A2 修复: 恢复原模块(定义处)
    from core.harness.knowledge.knowledge_quality import get_quality_signals  # P0-A2 修复: 恢复原模块(定义处)
    score = get_entity_quality_score(entity_uri, collection_id=collection)
    signals = get_quality_signals(entity_uri, limit=20, collection_id=collection)
    return {"quality": score, "recent_signals": signals}
