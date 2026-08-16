"""
Platform policy routes — tenant policy snapshot CRUD.

Migrated from aiPlat-core/core/api/routers/policy.py per architecture contract:
platform service endpoints should live in the platform layer, not core.
"""

from __future__ import annotations

from api.schemas_response import StatusResponse
from typing import Dict, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import rbac_guard
from core.api.facades.runtime_facade import KernelRuntime, get_kernel_runtime

router = APIRouter(prefix="/platform/policy", tags=["policy"])

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


@router.get("/snapshot", response_model=StatusResponse)
async def get_policy_snapshot(tenant_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    item = await store.get_tenant_policy(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    return item


@router.put("/snapshot", response_model=StatusResponse)
async def put_policy_snapshot(request: dict, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
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


@router.get("/versions", response_model=StatusResponse)
async def list_policy_versions(tenant_id: Optional[str] = None, rt: RuntimeDep = Depends(get_kernel_runtime)):
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


# ════════════════════════════════════════════════════════════════
# P1-A6: ManagedPolicy 端点 (仅 admin)
# ════════════════════════════════════════════════════════════════

@router.put("/managed", response_model=StatusResponse)
async def put_managed_policy(request: dict, http_request: Request,
                             rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Set enterprise-managed policy entries (admin only).

    Body: {"tenant_id": str, "policy": {"key": {"value": ..., "managed": true}}}
    Managed keys override local policy; local cannot relax managed entries.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tenant_id = (request or {}).get("tenant_id")
    policy = (request or {}).get("policy")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    if not isinstance(policy, dict):
        raise HTTPException(status_code=400, detail="policy must be an object")

    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="managed_policy_upsert",
        resource_type="tenant_policy",
        resource_id=str(tenant_id),
    )
    if deny:
        return deny

    # Merge managed entries into existing tenant policy
    existing = await store.get_tenant_policy(tenant_id=str(tenant_id))
    merged = dict((existing or {}).get("policy_json") or (existing or {}).get("policy") or {})
    for key, val in policy.items():
        if isinstance(val, dict):
            merged[key] = {"value": val.get("value"), "managed": True,
                           "source": val.get("source", "enterprise-admin")}
        else:
            merged[key] = {"value": val, "managed": True, "source": "enterprise-admin"}
    result = await store.upsert_tenant_policy(
        tenant_id=str(tenant_id), policy=merged,
        version=existing.get("version") if existing else None)
    # audit
    try:
        import logging
        logging.getLogger("aiplat.policy").info(
            "managed_policy_upsert tenant=%s keys=%s", tenant_id, list(policy.keys()))
    except Exception:
        pass  # noqa: audit-best-effort
    return result
