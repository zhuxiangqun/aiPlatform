"""audit_ops_export：评测服务模块。

职责：见同目录 README / 调用方。
"""

from __future__ import annotations

from typing import Dict, Annotated, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core.api.deps import rbac_guard
from core.api.core_facade import KernelRuntime  # P0-A2: 经 CoreFacade
from core.api.core_facade import get_kernel_runtime  # P0-A2: 经 CoreFacade

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


@router.get("/audit/logs", response_model=Dict[str, Any])
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
    """列出 audit_logs。

    Args:
        tenant_id: 租户 ID。
        actor_id: actor 标识。
        action: action 参数。
        resource_type: resource_type 参数。
        resource_id: resource 标识。
        request_id: request 标识。
        change_id: change 标识。
        run_id: 运行 ID。
        trace_id: trace 标识。
        status: 状态。
        created_after: created_after 参数。
        created_before: created_before 参数。
        limit: 返回条数上限。
        offset: 分页偏移。
        rt: rt 参数。
    """
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


@router.get("/audit/verify", response_model=Dict[str, Any])
async def verify_audit_chain(
    tenant_id: Optional[str] = None,
    rt: RuntimeDep = None,
):
    """Verify the tamper-evidence hash chain of the audit log for a tenant.

    Args:
        tenant_id: 租户 ID。
        rt: rt 参数。
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.verify_audit_chain(tenant_id=tenant_id)


@router.get("/ops/export/audit_logs.csv", response_model=Dict[str, Any])
async def export_audit_logs_csv(
    http_request: Request,
    tenant_id: Optional[str] = None,
    limit: int = 1000,
    rt: RuntimeDep = None,
):
    """export_audit_logs_csv。

    Args:
        http_request: http_request 参数。
        tenant_id: 租户 ID。
        limit: 返回条数上限。
        rt: rt 参数。
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="audit_logs")
    """export_audit_logs_csv。

    Args:
        http_request: http_request 参数。
        tenant_id: 租户 ID。
        limit: 返回条数上限。
        rt: rt 参数。
    """
    if deny:
        return deny

    from core.api.services import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_audit_logs_csv(tenant_id=tenant_id, limit=limit)
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
