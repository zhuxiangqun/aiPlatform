"""Ontology Editor — Metrics API endpoints (v2.7)."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request

# 为什么：走 apps.common_schemas，避免 `from api.*` 环依赖
from apps.common_schemas import StatusResponse
from auth.request_identity import resolve_request_tenant

router = APIRouter(tags=["ontology-editor-metrics"])


@router.get("/domains/{domain_id}/metrics", response_model=StatusResponse)
async def list_metrics(domain_id: str, request: Request):
    """List all metric definitions for a domain.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request；身份租户（N09 K18）。
    """
    try:
        tenant_id = resolve_request_tenant(request)
        from core.api.core_facade import get_ontology_domain_schema, load_metrics

        schema = get_ontology_domain_schema(domain_id)
        metrics = load_metrics(schema)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "metrics": [
                {
                    "name": m.name,
                    "label": m.label,
                    "binds_to": m.binds_to,
                    "aggregation": m.aggregation,
                    "unit": m.unit,
                }
                for m in metrics
            ],
            "total": len(metrics),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/metrics/{metric_name}/value", response_model=StatusResponse)
async def get_metric_value(
    domain_id: str,
    metric_name: str,
    request: Request,
    days: int = Query(30),
):
    """Get current metric value with threshold color.

    Args:
        domain_id: domain 标识。
        metric_name: metric_name 参数。
        request: FastAPI Request；身份租户（N09 K18）。
        days: days 参数。
    """
    try:
        tenant_id = resolve_request_tenant(request)
        from core.api.core_facade import get_ontology_domain_schema, compute, load_metrics

        schema = get_ontology_domain_schema(domain_id)
        metrics = {m.name: m for m in load_metrics(schema)}
        metric = metrics.get(metric_name)
        if not metric:
            raise HTTPException(status_code=404, detail=f"Metric not found: {metric_name}")
        # 为什么：N09 K18 — metric 计算须按身份租户过滤 state_changes
        result = compute(metric, domain_id, time_window_days=days, tenant_id=tenant_id)
        return {**result, "tenant_id": tenant_id, "domain_id": domain_id}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/metrics/{metric_name}/trend", response_model=StatusResponse)
async def get_metric_trend(
    domain_id: str,
    metric_name: str,
    request: Request,
    days: int = Query(30),
):
    """Get daily metric trend for the last N days.

    Args:
        domain_id: domain 标识。
        metric_name: metric_name 参数。
        request: FastAPI Request；身份租户（N09 K18）。
        days: days 参数。
    """
    try:
        tenant_id = resolve_request_tenant(request)
        from core.api.core_facade import get_ontology_domain_schema, get_trend, load_metrics

        schema = get_ontology_domain_schema(domain_id)
        metrics = {m.name: m for m in load_metrics(schema)}
        metric = metrics.get(metric_name)
        if not metric:
            raise HTTPException(status_code=404, detail=f"Metric not found: {metric_name}")
        trend = get_trend(metric, domain_id, days=days, tenant_id=tenant_id)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "metric": metric_name,
            "trend": trend,
            "days": days,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/metrics/scorecard", response_model=StatusResponse)
async def get_scorecard(domain_id: str, request: Request):
    """Get a scorecard of all metrics for a domain.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request；身份租户（N09 K18）。
    """
    try:
        tenant_id = resolve_request_tenant(request)
        from core.api.core_facade import get_ontology_domain_schema, scorecard, load_metrics

        schema = get_ontology_domain_schema(domain_id)
        metrics = load_metrics(schema)
        if not metrics:
            return {"domain_id": domain_id, "tenant_id": tenant_id, "scorecard": [], "total": 0}
        cards = scorecard(metrics, domain_id, tenant_id=tenant_id)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "scorecard": cards,
            "total": len(cards),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
