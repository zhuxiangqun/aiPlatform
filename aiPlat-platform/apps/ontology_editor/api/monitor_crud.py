u"""Ontology Editor — Process Monitor API endpoints (v2.6)."""
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

router = APIRouter(tags=["ontology-editor-monitor"])


@router.get("/domains/{domain_id}/monitor/state-distribution", response_model=Dict[str, Any])
async def state_distribution(domain_id: str):
    u"""Get per-class-per-state instance counts."""
    try:
        from core.api.core_facade import get_state_distribution
        data = get_state_distribution(domain_id)
        return {"domain_id": domain_id, "distribution": data, "total_classes": len(set(d.get("class_name", "") for d in data))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/bottlenecks", response_model=Dict[str, Any])
async def bottlenecks(domain_id: str, limit: int = Query(10)):
    u"""Top entities stuck longest in current state."""
    try:
        from core.api.core_facade import get_bottleneck_analysis
        data = get_bottleneck_analysis(domain_id, limit)
        return {"domain_id": domain_id, "bottlenecks": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/sla-violations", response_model=Dict[str, Any])
async def sla_violations(domain_id: str):
    u"""Recent SLA violations from time_elapsed triggers."""
    try:
        from core.api.core_facade import get_sla_violations
        data = get_sla_violations(domain_id)
        return {"domain_id": domain_id, "violations": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/trends", response_model=Dict[str, Any])
async def trends(domain_id: str, days: int = Query(7)):
    u"""Daily state transition trend data."""
    try:
        from core.api.core_facade import get_trend_data
        data = get_trend_data(domain_id, days)
        return {"domain_id": domain_id, "trends": data, "days": days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/process-status", response_model=Dict[str, Any])
async def process_status(domain_id: str, process_name: Optional[str] = Query(None)):
    u"""Get running process instance status."""
    try:
        from core.api.core_facade import get_process_status
        data = get_process_status(domain_id, process_name or "")
        return {"domain_id": domain_id, "processes": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/monitor/process-bottlenecks", response_model=Dict[str, Any])
async def process_bottlenecks(domain_id: str, limit: int = Query(10)):
    u"""Process instances stuck longest at their current step."""
    try:
        from core.api.core_facade import get_bottlenecks
        data = get_bottlenecks(domain_id, limit)
        return {"domain_id": domain_id, "bottlenecks": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
