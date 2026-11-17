"""Ontology Editor — Process Monitor API endpoints (v2.7 / N09 K11)."""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional

# 为什么：走 apps.common_schemas，避免 `from api.*` 触发 api/__init__→routes 环依赖
from apps.common_schemas import StatusResponse
from auth.request_identity import resolve_request_tenant

router = APIRouter(tags=["ontology-editor-monitor"])


def _is_not_initialized(e: Exception) -> bool:
    """Check if the error means the engine hasn't run yet (no data tables)."""
    msg = str(e).lower()
    return any(kw in msg for kw in ("no such table", "database is locked", "unable to open"))


@router.get("/domains/{domain_id}/monitor/state-distribution", response_model=StatusResponse)
async def state_distribution(domain_id: str, request: Request):
    """Get per-class-per-state instance counts.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request（经身份解析取 tenant）。
    """
    try:
        from core.api.core_facade import get_state_distribution
        # 为什么：N09 K11 — monitor 读路径须按租户过滤 state_changes
        tenant_id = resolve_request_tenant(request)
        data = get_state_distribution(domain_id, tenant_id=tenant_id)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "distribution": data,
            "total_classes": len(set(d.get("class_name", "") for d in data)),
        }
    except Exception as e:
        if _is_not_initialized(e):
            return {
                "domain_id": domain_id,
                "tenant_id": resolve_request_tenant(request),
                "distribution": [],
                "total_classes": 0,
                "status": "engine_not_run",
            }
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/bottlenecks", response_model=StatusResponse)
async def bottlenecks(domain_id: str, request: Request, limit: int = Query(10)):
    """Top entities stuck longest in current state.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request（经身份解析取 tenant）。
        limit: 返回条数上限。
    """
    try:
        from core.api.core_facade import get_bottleneck_analysis
        tenant_id = resolve_request_tenant(request)
        data = get_bottleneck_analysis(domain_id, limit, tenant_id=tenant_id)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "bottlenecks": data,
            "total": len(data),
        }
    except Exception as e:
        if _is_not_initialized(e):
            return {
                "domain_id": domain_id,
                "tenant_id": resolve_request_tenant(request),
                "bottlenecks": [],
                "total": 0,
                "status": "engine_not_run",
            }
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/sla-violations", response_model=StatusResponse)
async def sla_violations(domain_id: str, request: Request):
    """Recent SLA violations from time_elapsed triggers.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request（经身份解析取 tenant）。
    """
    try:
        from core.api.core_facade import get_sla_violations
        tenant_id = resolve_request_tenant(request)
        data = get_sla_violations(domain_id, tenant_id=tenant_id)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "violations": data,
            "total": len(data),
        }
    except Exception as e:
        if _is_not_initialized(e):
            return {
                "domain_id": domain_id,
                "tenant_id": resolve_request_tenant(request),
                "violations": [],
                "total": 0,
                "status": "engine_not_run",
            }
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/trends", response_model=StatusResponse)
async def trends(domain_id: str, request: Request, days: int = Query(7)):
    """Daily state transition trend data.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request（经身份解析取 tenant）。
        days: days 参数。
    """
    try:
        from core.api.core_facade import get_trend_data
        tenant_id = resolve_request_tenant(request)
        data = get_trend_data(domain_id, days, tenant_id=tenant_id)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "trends": data,
            "days": days,
        }
    except Exception as e:
        if _is_not_initialized(e):
            return {
                "domain_id": domain_id,
                "tenant_id": resolve_request_tenant(request),
                "trends": [],
                "days": days,
                "status": "engine_not_run",
            }
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/process-status", response_model=StatusResponse)
async def process_status(
    domain_id: str, request: Request, process_name: Optional[str] = Query(None)
):
    """Get running process instance status.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request（身份解析；process_instances 物理 tenant 仍属未做）。
        process_name: process_name 参数。
    """
    try:
        from core.api.core_facade import get_process_status
        tenant_id = resolve_request_tenant(request)
        data = get_process_status(domain_id, process_name or "", tenant_id=tenant_id)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "processes": data,
            "total": len(data),
        }
    except Exception as e:
        if _is_not_initialized(e):
            return {
                "domain_id": domain_id,
                "tenant_id": resolve_request_tenant(request),
                "processes": [],
                "total": 0,
                "status": "engine_not_run",
            }
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/process-bottlenecks", response_model=StatusResponse)
async def process_bottlenecks(domain_id: str, request: Request, limit: int = Query(10)):
    """Process instances stuck longest at their current step.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request（身份解析；process_instances 物理 tenant 仍属未做）。
        limit: 返回条数上限。
    """
    try:
        from core.api.core_facade import get_bottlenecks
        tenant_id = resolve_request_tenant(request)
        data = get_bottlenecks(domain_id, limit, tenant_id=tenant_id)
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "bottlenecks": data,
            "total": len(data),
        }
    except Exception as e:
        if _is_not_initialized(e):
            return {
                "domain_id": domain_id,
                "tenant_id": resolve_request_tenant(request),
                "bottlenecks": [],
                "total": 0,
                "status": "engine_not_run",
            }
        raise HTTPException(status_code=500, detail=str(e))
