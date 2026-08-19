from api.schemas_response import StatusResponse
u"""Ontology Editor — Metrics API endpoints (v2.7)."""
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

router = APIRouter(tags=["ontology-editor-metrics"])


@router.get("/domains/{domain_id}/metrics", response_model=StatusResponse)
async def list_metrics(domain_id: str):
    u"""List all metric definitions for a domain."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        from core.api.core_facade import load_metrics
        metrics = load_metrics(schema)
        return {
            "domain_id": domain_id,
            "metrics": [{"name": m.name, "label": m.label, "binds_to": m.binds_to,
                          "aggregation": m.aggregation, "unit": m.unit} for m in metrics],
            "total": len(metrics),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/metrics/{metric_name}/value", response_model=StatusResponse)
async def get_metric_value(domain_id: str, metric_name: str, days: int = Query(30)):
    u"""Get current metric value with threshold color."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        from core.api.core_facade import compute  # P0-A2 修复: CoreFacade 已补 re-export
        from core.api.core_facade import load_metrics
        metrics = {m.name: m for m in load_metrics(schema)}
        metric = metrics.get(metric_name)
        if not metric:
            raise HTTPException(status_code=404, detail=f"Metric not found: {metric_name}")
        result = compute(metric, domain_id, time_window_days=days)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/metrics/{metric_name}/trend", response_model=StatusResponse)
async def get_metric_trend(domain_id: str, metric_name: str, days: int = Query(30)):
    u"""Get daily metric trend for the last N days."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        from core.api.core_facade import get_trend
        from core.api.core_facade import load_metrics
        metrics = {m.name: m for m in load_metrics(schema)}
        metric = metrics.get(metric_name)
        if not metric:
            raise HTTPException(status_code=404, detail=f"Metric not found: {metric_name}")
        trend = get_trend(metric, domain_id, days=days)
        return {"domain_id": domain_id, "metric": metric_name, "trend": trend, "days": days}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/metrics/scorecard", response_model=StatusResponse)
async def get_scorecard(domain_id: str):
    u"""Get a scorecard of all metrics for a domain."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        from core.api.core_facade import scorecard
        from core.api.core_facade import load_metrics
        metrics = load_metrics(schema)
        if not metrics:
            return {"domain_id": domain_id, "scorecard": [], "total": 0}
        cards = scorecard(metrics, domain_id)
        return {"domain_id": domain_id, "scorecard": cards, "total": len(cards)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
