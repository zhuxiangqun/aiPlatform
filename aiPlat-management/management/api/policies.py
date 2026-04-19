from fastapi import APIRouter, HTTPException, Query
import httpx

from management.api.core import get_core_client

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/tenants")
async def list_tenant_policies(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    try:
        client = get_core_client()
        return await client._request("GET", "/api/core/policies/tenants", params={"limit": limit, "offset": offset})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/tenants/{tenant_id}")
async def get_tenant_policy(tenant_id: str):
    try:
        client = get_core_client()
        return await client._request("GET", f"/api/core/policies/tenants/{tenant_id}")
    except httpx.HTTPStatusError as e:
        status = getattr(getattr(e, "response", None), "status_code", 500)
        raise HTTPException(status_code=int(status), detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.put("/tenants/{tenant_id}")
async def upsert_tenant_policy(tenant_id: str, body: dict):
    try:
        client = get_core_client()
        return await client._request("PUT", f"/api/core/policies/tenants/{tenant_id}", json=body or {})
    except httpx.HTTPStatusError as e:
        status = getattr(getattr(e, "response", None), "status_code", 500)
        raise HTTPException(status_code=int(status), detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")


@router.get("/tenants/{tenant_id}/evaluate-tool")
async def evaluate_tenant_tool_policy(tenant_id: str, tool_name: str):
    try:
        client = get_core_client()
        return await client._request("GET", f"/api/core/policies/tenants/{tenant_id}/evaluate-tool", params={"tool_name": tool_name})
    except httpx.HTTPStatusError as e:
        status = getattr(getattr(e, "response", None), "status_code", 500)
        raise HTTPException(status_code=int(status), detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core API unavailable: {str(e)}")
