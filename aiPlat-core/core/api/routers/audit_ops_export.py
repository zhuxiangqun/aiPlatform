from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core.api.deps.rbac import rbac_guard
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


@router.get("/audit/logs")
async def list_audit_logs(
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    request_id: Optional[str] = None,
    change_id: Optional[str] = None,
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    status: Optional[str] = None,
    created_after: Optional[float] = None,
    created_before: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_audit_logs(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        change_id=change_id,
        run_id=run_id,
        trace_id=trace_id,
        status=status,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )


@router.get("/ops/export/audit_logs.csv")
async def export_audit_logs_csv(
    http_request: Request,
    tenant_id: Optional[str] = None,
    limit: int = 1000,
    rt: RuntimeDep = None,
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="audit_logs")
    if deny:
        return deny

    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_audit_logs_csv(tenant_id=tenant_id, limit=limit)
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

