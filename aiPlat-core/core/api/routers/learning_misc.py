from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import actor_from_http
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _approval_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "approval_manager", None) if rt else None


# ==================== Learning artifacts ====================


@router.get("/learning/artifacts")
async def list_learning_artifacts(
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    """List learning_artifacts stored in ExecutionStore."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_learning_artifacts(
        target_type=target_type,
        target_id=target_id,
        kind=kind,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )


@router.get("/learning/artifacts/{artifact_id}")
async def get_learning_artifact(artifact_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    art = await store.get_learning_artifact(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return art


@router.post("/learning/artifacts/{artifact_id}/status")
async def set_learning_artifact_status(artifact_id: str, request: dict, rt: RuntimeDep = None):
    """Update artifact status + merge metadata (status transitions only)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.manager import LearningManager

    status = (request or {}).get("status")
    if not isinstance(status, str) or not status:
        raise HTTPException(status_code=400, detail="missing_status")
    metadata_update = (request or {}).get("metadata_update") if isinstance((request or {}).get("metadata_update"), dict) else {}
    mgr = LearningManager(execution_store=store)
    await mgr.set_artifact_status(artifact_id=artifact_id, status=status, metadata_update=metadata_update)
    return {"status": "ok", "artifact_id": artifact_id, "new_status": status}


# ==================== Release rollouts / metrics snapshots ====================


@router.get("/learning/rollouts")
async def list_release_rollouts(
    http_request: Request,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, None)
    tid = actor0.get("tenant_id")
    return await store.list_release_rollouts(tenant_id=str(tid) if tid else None, target_type=target_type, target_id=target_id, limit=limit, offset=offset)


@router.put("/learning/rollouts")
async def upsert_release_rollout(request: dict, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tid = actor0.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id required")
    target_type = (request or {}).get("target_type")
    target_id = (request or {}).get("target_id")
    candidate_id = (request or {}).get("candidate_id")
    if not target_type or not target_id or not candidate_id:
        raise HTTPException(status_code=400, detail="target_type,target_id,candidate_id required")
    rr = await store.upsert_release_rollout(
        tenant_id=str(tid),
        target_type=str(target_type),
        target_id=str(target_id),
        candidate_id=str(candidate_id),
        mode=str((request or {}).get("mode") or "percentage"),
        percentage=(request or {}).get("percentage"),
        include_actor_ids=(request or {}).get("include_actor_ids"),
        exclude_actor_ids=(request or {}).get("exclude_actor_ids"),
        enabled=bool((request or {}).get("enabled", True)),
        metadata=(request or {}).get("metadata") if isinstance((request or {}).get("metadata"), dict) else None,
    )
    return {"status": "ok", "rollout": rr}


@router.delete("/learning/rollouts")
async def delete_release_rollout(request: dict, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tid = actor0.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id required")
    target_type = (request or {}).get("target_type")
    target_id = (request or {}).get("target_id")
    if not target_type or not target_id:
        raise HTTPException(status_code=400, detail="target_type,target_id required")
    ok = await store.delete_release_rollout(tenant_id=str(tid), target_type=str(target_type), target_id=str(target_id))
    return {"status": "deleted" if ok else "not_found"}


@router.post("/learning/releases/{candidate_id}/metrics/snapshots")
async def add_release_metric_snapshot(candidate_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tid = actor0.get("tenant_id")
    metric_key = (request or {}).get("metric_key")
    value = (request or {}).get("value")
    if not metric_key or value is None:
        raise HTTPException(status_code=400, detail="metric_key and value are required")
    try:
        val = float(value)
    except Exception:
        raise HTTPException(status_code=400, detail="value must be number")
    rec = await store.add_release_metric_snapshot(
        tenant_id=str(tid) if tid else None,
        candidate_id=str(candidate_id),
        metric_key=str(metric_key),
        value=val,
        window_start=(request or {}).get("window_start"),
        window_end=(request or {}).get("window_end"),
        metadata=(request or {}).get("metadata") if isinstance((request or {}).get("metadata"), dict) else None,
    )
    return {"status": "created", "snapshot": rec}


@router.get("/learning/releases/{candidate_id}/metrics/snapshots")
async def list_release_metric_snapshots(
    candidate_id: str,
    http_request: Request,
    metric_key: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, None)
    tid = actor0.get("tenant_id")
    return await store.list_release_metric_snapshots(tenant_id=str(tid) if tid else None, candidate_id=str(candidate_id), metric_key=metric_key, limit=limit, offset=offset)


@router.post("/learning/releases/expire")
async def expire_releases(request: dict, rt: RuntimeDep = None):
    """Expire published release candidates based on metadata.expires_at (offline status transitions only)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.manager import LearningManager

    mgr = LearningManager(execution_store=store)
    now = float((request or {}).get("now") or time.time())
    dry_run = bool((request or {}).get("dry_run", False))
    target_type = (request or {}).get("target_type")
    target_id = (request or {}).get("target_id")

    res = await store.list_learning_artifacts(target_type=target_type, target_id=target_id, kind="release_candidate", status="published", limit=2000, offset=0)
    items = res.get("items") or []
    rolled_back = []
    kept = []
    for cand in items:
        meta = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else {}
        exp = meta.get("expires_at")
        try:
            exp_ts = float(exp) if exp is not None else None
        except Exception:
            exp_ts = None
        if exp_ts is None or exp_ts > now:
            kept.append(cand.get("artifact_id"))
            continue
        cid = cand.get("artifact_id")
        if not isinstance(cid, str) or not cid:
            continue
        if dry_run:
            rolled_back.append(cid)
            continue
        await mgr.set_artifact_status(artifact_id=cid, status="rolled_back", metadata_update={"rolled_back_via": "expire_releases", "rolled_back_at": now})
        rolled_back.append(cid)

    return {"now": now, "dry_run": dry_run, "rolled_back": rolled_back, "kept": kept}


# ==================== Auto rollback / approvals cleanup ====================


@router.post("/learning/auto-rollback/regression")
async def api_auto_rollback_regression(request: dict, rt: RuntimeDep = None):
    """HTTP wrapper for auto-rollback-regression (offline) used by management plane."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    approval_mgr = _approval_mgr(rt)
    if not approval_mgr:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    from core.learning.autorollback import auto_rollback_regression

    agent_id = (request or {}).get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise HTTPException(status_code=400, detail="missing_agent_id")

    return await auto_rollback_regression(
        store=store,
        approval_manager=approval_mgr,
        agent_id=agent_id,
        candidate_id=(request or {}).get("candidate_id"),
        baseline_candidate_id=(request or {}).get("baseline_candidate_id"),
        current_window=int((request or {}).get("current_window", 50) or 50),
        baseline_window=int((request or {}).get("baseline_window", 50) or 50),
        min_samples=int((request or {}).get("min_samples", 10) or 10),
        error_rate_delta_threshold=float((request or {}).get("error_rate_delta_threshold", 0.1) or 0.1),
        avg_duration_delta_threshold=(float((request or {}).get("avg_duration_delta_threshold")) if (request or {}).get("avg_duration_delta_threshold") is not None else None),
        link_baseline=bool((request or {}).get("link_baseline", False)),
        max_linked_evidence=int((request or {}).get("max_linked_evidence", 200) or 200),
        require_approval=bool((request or {}).get("require_approval", False)),
        approval_request_id=(request or {}).get("approval_request_id"),
        user_id=(request or {}).get("user_id") or "system",
        dry_run=bool((request or {}).get("dry_run", False)),
        now=(float((request or {}).get("now")) if (request or {}).get("now") is not None else None),
    )


@router.post("/learning/approvals/cleanup-rollback-approvals")
async def api_cleanup_rollback_approvals(request: dict, rt: RuntimeDep = None):
    """HTTP wrapper for cleanup-rollback-approvals."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    approval_mgr = _approval_mgr(rt)
    if not approval_mgr:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    from core.learning.autorollback import cleanup_rollback_approvals

    return await cleanup_rollback_approvals(
        store=store,
        approval_manager=approval_mgr,
        now=(float((request or {}).get("now")) if (request or {}).get("now") is not None else None),
        dry_run=bool((request or {}).get("dry_run", False)),
        user_id=(request or {}).get("user_id"),
        candidate_id=(request or {}).get("candidate_id"),
        page_size=int((request or {}).get("page_size", 500) or 500),
    )

