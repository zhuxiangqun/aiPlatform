"""
Wiki Ontology Patterns API — pattern detector, metrics, and regression testing.
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import logging

router = APIRouter(tags=["wiki-ontology-patterns"])

# ── Pattern Detector (Ontology Evolution Layer 1) ─────────────────

@router.get("/patterns", response_model=Dict[str, Any])
async def detect_patterns(collection: str = "default"):
    """Scan wiki data and detect patterns not yet covered by T-Box.

    Returns:
    - undefined_categories: categories used in wiki but not in any T-Box class
    - tag_clusters: high-frequency tags that may warrant new ontology classes
    - dangling_references: pages referencing titles that don't exist (with variant suggestions)
    - category_gaps: T-Box classes with zero wiki pages
    - undefined_relations: relationship types in pages not in OBJECT_PROPERTIES
    """
    try:
        from core.harness.knowledge.knowledge_validator import detect_ontology_patterns
        patterns = detect_ontology_patterns(collection_id=collection)
        return {
            "summary": patterns.summary,
            "scanned_pages": patterns.scanned_pages,
            "scanned_collections": patterns.scanned_collections,
            "undefined_categories": patterns.undefined_categories,
            "undefined_relations": patterns.undefined_relations,
            "tag_clusters": patterns.tag_clusters,
            "dangling_references": patterns.dangling_references,
            "category_gaps": patterns.category_gaps,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pattern detection failed: {e}")


@router.get("/metrics", response_model=Dict[str, Any])
async def get_ontology_metrics(collection: str = "default", refresh: bool = False):
    """Four-dimension ontology health metrics (cache-backed).

    Dimensions:
    1. Coverage: % wiki pages covered by T-Box classes
    2. Consistency: validator errors / warnings / score
    3. Inference gain: transitive + source_chain edges inferred
    4. Maintenance cost: pending suggestions + last review time
    Class usage: per-class wiki page counts

    Cache is auto-invalidated when wiki pages are created/updated/deleted,
    then rebuilt in a background subprocess. refresh=true shows cache age.
    """
    try:
        from core.harness.knowledge.knowledge_validator import load_metrics_cache
        import time as _time, os as _os

        if refresh:
            # Invalidate cache and trigger background rebuild
            cache_path = _os.path.join(_os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat")),
                                        "wiki", "collections", collection, "metrics_cache.json")
            try:
                if _os.path.exists(cache_path):
                    _os.remove(cache_path)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            from core.harness.knowledge._bg_tasks import enqueue
            enqueue("rebuild_metrics", collection_id=collection)
            return {"source": "recomputing", "message": "后台重新计算中，请稍后刷新。预计 1-3 分钟完成。"}

        cached = load_metrics_cache(collection)
        if cached and "metrics" in cached:
            age = round(_time.time() - cached.get("computed_at", _time.time()), 0)
            return {"source": "cache", "cache_age_seconds": age, **cached["metrics"]}
        return {"source": "pending", "message": "Metrics not yet computed. Click '刷新指标' to trigger rebuild.", "consistency": {"score": 0, "errors": 0}, "coverage": {"percentage": 0, "covered": 0, "total": 0}, "inference_gain": {"summary": "pending", "total_inferred": 0}, "maintenance_cost": {"pending_suggestions": 0}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics failed: {e}")


@router.get("/metrics/history", response_model=Dict[str, Any])
async def get_metrics_history(collection: str = "default"):
    """Return historical metrics snapshots for trend analysis (last 30 days)."""
    try:
        from core.harness.knowledge.knowledge_validator import load_metrics_history
        history = load_metrics_history(collection)
        return {"history": history, "total": len(history)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"History failed: {e}")


@router.get("/golden-regression", response_model=Dict[str, Any])
async def run_golden_regression(collection: str = "default", min_score: float = None, strict: bool = False):
    """Run golden query regression test to validate retrieval quality.

    Uses golden_queries.yaml (8 queries) to check whether wiki retrieval
    returns expected concepts. Returns pass rate and per-query details.

    Args:
        min_score: Custom min_wiki_score threshold (overrides strict).
        strict: Use production threshold (0.3) instead of test threshold (0.1).
    """
    try:
        from core.harness.knowledge.knowledge_validator import run_golden_query_regression
        result = run_golden_query_regression(collection_id=collection, min_score=min_score, strict_mode=strict)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regression failed: {e}")
