from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import rbac_guard
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


@router.get("/policy/snapshot")
async def get_policy_snapshot(tenant_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    item = await store.get_tenant_policy(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    return item


@router.put("/policy/snapshot")
async def put_policy_snapshot(request: dict, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tenant_id = (request or {}).get("tenant_id")
    policy = (request or {}).get("policy")
    version = (request or {}).get("version")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    if not isinstance(policy, dict):
        raise HTTPException(status_code=400, detail="policy must be an object")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="policy_upsert",
        resource_type="tenant_policy",
        resource_id=str(tenant_id),
    )
    if deny:
        return deny
    if version is not None:
        try:
            version = int(version)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid version")
    return await store.upsert_tenant_policy(tenant_id=str(tenant_id), policy=policy, version=version)


@router.get("/policy/versions")
async def list_policy_versions(tenant_id: Optional[str] = None, rt: RuntimeDep = None):
    """
    MVP：tenant_policies 仅保存最新 version，因此 versions 返回 [current]。
    后续可扩展为历史版本表 policy_snapshots。
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    if tenant_id:
        item = await store.get_tenant_policy(tenant_id=str(tenant_id))
        if not item:
            return {"tenant_id": str(tenant_id), "versions": []}
        return {"tenant_id": str(tenant_id), "versions": [item.get("version")]}
    items = await store.list_tenant_policies(limit=200, offset=0)
    out = []
    for it in (items.get("items") or []):
        if isinstance(it, dict) and it.get("tenant_id"):
            out.append({"tenant_id": it.get("tenant_id"), "version": it.get("version")})
    return {"items": out}

