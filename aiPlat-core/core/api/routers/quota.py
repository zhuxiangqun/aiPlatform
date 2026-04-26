from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


@router.get("/quota/snapshot")
async def get_quota_snapshot(tenant_id: str, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(
        http_request=http_request,
        payload=None,
        action="quota_read",
        resource_type="tenant_quota",
        resource_id=str(tenant_id),
    )
    if deny:
        return deny
    item = await store.get_tenant_quota(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_quota_not_found")
    return item


@router.put("/quota/snapshot")
async def put_quota_snapshot(request: dict, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tenant_id = (request or {}).get("tenant_id")
    quota = (request or {}).get("quota")
    version = (request or {}).get("version")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    if not isinstance(quota, dict):
        raise HTTPException(status_code=400, detail="quota must be an object")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="quota_upsert",
        resource_type="tenant_quota",
        resource_id=str(tenant_id),
    )
    if deny:
        return deny
    if version is not None:
        try:
            version = int(version)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid version")
    saved = await store.upsert_tenant_quota(tenant_id=str(tenant_id), quota=quota, version=version)
    try:
        actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
        await store.add_audit_log(
            action="tenant_quota_upsert",
            status="ok",
            tenant_id=str(tenant_id),
            actor_id=str(actor0.get("actor_id") or "system"),
            actor_role=str(actor0.get("actor_role") or "") or None,
            resource_type="tenant_quota",
            resource_id=str(tenant_id),
            detail={"version": saved.get("version")},
        )
    except Exception:
        pass
    return saved


@router.get("/quota/usage")
async def get_quota_usage(
    http_request: Request,
    tenant_id: str,
    day_start: Optional[str] = None,
    day_end: Optional[str] = None,
    metric_key: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(
        http_request=http_request,
        payload=None,
        action="quota_usage_read",
        resource_type="tenant_quota",
        resource_id=str(tenant_id),
    )
    if deny:
        return deny
    return await store.list_tenant_usage(
        tenant_id=str(tenant_id),
        day_start=day_start,
        day_end=day_end,
        metric_key=metric_key,
        limit=limit,
        offset=offset,
    )

