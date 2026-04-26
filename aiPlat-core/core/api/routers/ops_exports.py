from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


@router.post("/ops/prune")
async def ops_prune(request: dict, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """
    Trigger ExecutionStore.prune() manually (best-effort).
    Use RBAC guard: action=ops_prune.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=request, action="ops_prune", resource_type="ops", resource_id="prune")
    if deny:
        return deny
    now_ts = (request or {}).get("now_ts")
    try:
        now_ts = float(now_ts) if now_ts is not None else None
    except Exception:
        now_ts = None
    res = await store.prune(now_ts=now_ts)
    try:
        actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
        await store.add_audit_log(
            action="ops_prune",
            status="ok",
            tenant_id=actor0.get("tenant_id"),
            actor_id=str(actor0.get("actor_id") or "system"),
            actor_role=str(actor0.get("actor_role") or "") or None,
            resource_type="ops",
            resource_id="prune",
            detail=res,
        )
    except Exception:
        pass
    return {"ok": True, "deleted": res}


@router.get("/ops/export/run_events.csv")
async def export_run_events_csv(http_request: Request, run_id: str, limit: int = 5000, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="run_events")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_run_events_csv(run_id=run_id, limit=limit)
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/syscall_events.csv")
async def export_syscall_events_csv(
    http_request: Request,
    tenant_id: Optional[str] = None,
    run_id: Optional[str] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 2000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="syscall_events")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_syscall_events_csv(
        tenant_id=tenant_id, run_id=run_id, kind=kind, status=status, limit=limit
    )
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/approvals.csv")
async def export_approvals_csv(http_request: Request, tenant_id: Optional[str] = None, status: Optional[str] = None, limit: int = 1000, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="approvals")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_approvals_csv(tenant_id=tenant_id, status=status, limit=limit)
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/tenant_usage.csv")
async def export_tenant_usage_csv(
    http_request: Request,
    tenant_id: str,
    day_start: Optional[str] = None,
    day_end: Optional[str] = None,
    metric_key: Optional[str] = None,
    limit: int = 2000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="tenant_usage")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_tenant_usage_csv(
        tenant_id=tenant_id, day_start=day_start, day_end=day_end, metric_key=metric_key, limit=limit
    )
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/gateway_dlq.csv")
async def export_gateway_dlq_csv(
    http_request: Request,
    status: Optional[str] = None,
    tenant_id: Optional[str] = None,
    connector: Optional[str] = None,
    limit: int = 2000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="gateway_dlq")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_gateway_dlq_csv(
        status=status, tenant_id=tenant_id, connector=connector, limit=limit
    )
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/connector_attempts.csv")
async def export_connector_attempts_csv(
    http_request: Request,
    connector: Optional[str] = None,
    tenant_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 2000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="connector_attempts")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_connector_attempts_csv(
        connector=connector, tenant_id=tenant_id, run_id=run_id, status=status, limit=limit
    )
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/jobs_dlq.csv")
async def export_jobs_dlq_csv(
    http_request: Request,
    status: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 2000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="jobs_dlq")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_jobs_dlq_csv(status=status, job_id=job_id, limit=limit)
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/job_delivery_attempts.csv")
async def export_job_delivery_attempts_csv(
    http_request: Request,
    job_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 2000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="job_delivery_attempts")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_job_delivery_attempts_csv(
        job_id=job_id, run_id=run_id, status=status, limit=limit
    )
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/gateway_pairings.csv")
async def export_gateway_pairings_csv(
    http_request: Request,
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 5000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="gateway_pairings")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_gateway_pairings_csv(channel=channel, user_id=user_id, limit=limit)
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/gateway_tokens.csv")
async def export_gateway_tokens_csv(
    http_request: Request,
    enabled: Optional[bool] = None,
    limit: int = 5000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="gateway_tokens")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_gateway_tokens_csv(enabled=enabled, limit=limit)
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/release_rollouts.csv")
async def export_release_rollouts_csv(
    http_request: Request,
    tenant_id: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = 5000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="release_rollouts")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_release_rollouts_csv(
        tenant_id=tenant_id, target_type=target_type, target_id=target_id, limit=limit
    )
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/release_metrics.csv")
async def export_release_metrics_csv(
    http_request: Request,
    tenant_id: str,
    candidate_id: str,
    metric_key: Optional[str] = None,
    limit: int = 5000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="release_metrics")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_release_metrics_csv(
        tenant_id=tenant_id, candidate_id=candidate_id, metric_key=metric_key, limit=limit
    )
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/learning_artifacts.csv")
async def export_learning_artifacts_csv(
    http_request: Request,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = 5000,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="learning_artifacts")
    if deny:
        return deny
    from core.apps.ops import OpsExporter

    data, filename = await OpsExporter(execution_store=store).export_learning_artifacts_csv(
        target_type=target_type,
        target_id=target_id,
        kind=kind,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        limit=limit,
    )
    return Response(content=data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'})


@router.get("/ops/export/bundle.zip")
async def export_ops_bundle_zip(
    http_request: Request,
    tenant_id: str,
    day_start: Optional[str] = None,
    day_end: Optional[str] = None,
    run_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    include: Optional[str] = None,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    """
    PR-14+: 打包导出常用运维 CSV 为 zip。
    注意：仅打包“常用集合”，避免参数爆炸；更复杂的组合可按单文件导出。
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=None, action="ops_export", resource_type="ops", resource_id="bundle")
    if deny:
        return deny

    import io
    import zipfile

    from core.apps.ops import OpsExporter

    exp = OpsExporter(execution_store=store)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        include_set = set()
        if include:
            include_set = {x.strip() for x in str(include).split(",") if x.strip()}
        if not include_set:
            include_set = {
                "audit_logs",
                "syscall_events",
                "approvals",
                "tenant_usage",
                "gateway_dlq",
                "connector_attempts",
                "jobs_dlq",
                "release_rollouts",
            }
            if run_id:
                include_set.add("run_events")
            if candidate_id:
                include_set.add("release_metrics")

        async def _add(key: str):
            if key == "audit_logs":
                return await exp.export_audit_logs_csv(tenant_id=tenant_id, limit=5000)
            if key == "syscall_events":
                return await exp.export_syscall_events_csv(tenant_id=tenant_id, limit=5000)
            if key == "approvals":
                return await exp.export_approvals_csv(tenant_id=tenant_id, limit=5000)
            if key == "tenant_usage":
                return await exp.export_tenant_usage_csv(
                    tenant_id=tenant_id, day_start=day_start, day_end=day_end, metric_key=None, limit=5000
                )
            if key == "gateway_dlq":
                return await exp.export_gateway_dlq_csv(status="pending", tenant_id=tenant_id, connector=None, limit=5000)
            if key == "connector_attempts":
                return await exp.export_connector_attempts_csv(tenant_id=tenant_id, connector=None, run_id=None, status=None, limit=5000)
            if key == "jobs_dlq":
                return await exp.export_jobs_dlq_csv(status="pending", job_id=None, limit=5000)
            if key == "run_events":
                if not run_id:
                    return None
                return await exp.export_run_events_csv(run_id=run_id, limit=5000)
            if key == "release_rollouts":
                return await exp.export_release_rollouts_csv(tenant_id=tenant_id, target_type=None, target_id=None, limit=5000)
            if key == "release_metrics":
                if not candidate_id:
                    return None
                return await exp.export_release_metrics_csv(tenant_id=tenant_id, candidate_id=candidate_id, metric_key=None, limit=5000)
            if key == "gateway_tokens":
                return await exp.export_gateway_tokens_csv(enabled=None, limit=5000)
            if key == "gateway_pairings":
                return await exp.export_gateway_pairings_csv(channel=None, user_id=None, limit=5000)
            return None

        for k in sorted(include_set):
            item = await _add(k)
            if item:
                data, fname = item
                z.writestr(fname, data)

    content = buf.getvalue()
    fname = f"ops_bundle_{tenant_id}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename=\"{fname}\"'},
    )

