from fastapi import APIRouter, HTTPException, Query
import httpx

from management.api.core import get_core_client

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
async def list_audit_logs(
    tenant_id: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    request_id: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    status: str | None = None,
    created_after: float | None = None,
    created_before: float | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    try:
        client = get_core_client()
        params = {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "request_id": request_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "status": status,
            "created_after": created_after,
            "created_before": created_before,
            "limit": limit,
            "offset": offset,
        }
        params = {k: v for k, v in params.items() if v is not None}
        return await client._request("GET", "/api/core/audit/logs", params=params)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")
