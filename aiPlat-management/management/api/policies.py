"""policies：模块接口。"""

from fastapi import APIRouter, HTTPException, Query
import httpx

from management.api.core import get_core_client
from management.core_client import CoreAPIError

router = APIRouter(prefix="/policies", tags=["policies"])

# Policies were migrated to platform — proxy via _platform_req
_POLICIES_BASE = "/platform/tenant-policies/policies/tenants"


@router.get("/tenants")
async def list_tenant_policies(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    """列出 tenant_policies。

    Args:
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    try:
        client = get_core_client()
        return await client._platform_req("GET", f"{_POLICIES_BASE}", params={"limit": limit, "offset": offset})
    except CoreAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Platform API unavailable: {str(e)}")


@router.get("/tenants/{tenant_id}")
async def get_tenant_policy(tenant_id: str):
    """获取 tenant_policy。

    Args:
        tenant_id: 租户 ID。
    """
    try:
        client = get_core_client()
        return await client._platform_req("GET", f"{_POLICIES_BASE}/{tenant_id}")
    except CoreAPIError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="Tenant policy not found")
        raise HTTPException(status_code=e.status_code, detail=e.payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Platform API unavailable: {str(e)}")


@router.put("/tenants/{tenant_id}")
async def upsert_tenant_policy(tenant_id: str, body: dict):
    """upsert_tenant_policy。

    Args:
        tenant_id: 租户 ID。
        body: 请求体。
    """
    try:
        client = get_core_client()
        return await client._platform_req("PUT", f"{_POLICIES_BASE}/{tenant_id}", json=body or {})
    except httpx.HTTPStatusError as e:
        status = getattr(getattr(e, "response", None), "status_code", 500)
        raise HTTPException(status_code=int(status), detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Platform API unavailable: {str(e)}")


@router.get("/tenants/{tenant_id}/evaluate-tool")
async def evaluate_tenant_tool_policy(tenant_id: str, tool_name: str):
    """evaluate_tenant_tool_policy。

    Args:
        tenant_id: 租户 ID。
        tool_name: tool_name 参数。
    """
    try:
        client = get_core_client()
        return await client._platform_req("GET", f"{_POLICIES_BASE}/{tenant_id}/evaluate-tool", params={"tool_name": tool_name})
    except httpx.HTTPStatusError as e:
        status = getattr(getattr(e, "response", None), "status_code", 500)
        raise HTTPException(status_code=int(status), detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Platform API unavailable: {str(e)}")


@router.post("/evaluate")
async def evaluate_policy(body: dict):
    """evaluate_policy。

    Args:
        body: 请求体。
    """
    try:
        client = get_core_client()
        return await client._platform_req("POST", "/platform/tenant-policies/policies/evaluate", json=body or {})
    except httpx.HTTPStatusError as e:
        status = getattr(getattr(e, "response", None), "status_code", 500)
        raise HTTPException(status_code=int(status), detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Platform API unavailable: {str(e)}")
