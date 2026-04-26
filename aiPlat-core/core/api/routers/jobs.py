from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException

from core.harness.kernel.runtime import get_kernel_runtime
from core.management.job_scheduler import next_run_from_cron
from core.schemas import JobCreateRequest, JobUpdateRequest


router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _scheduler():
    rt = _rt()
    return getattr(rt, "job_scheduler", None) if rt else None


# ==================== Jobs / Cron (Roadmap-3) ====================


@router.get("/jobs")
async def list_jobs(limit: int = 100, offset: int = 0, enabled: Optional[bool] = None):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_jobs(limit=limit, offset=offset, enabled=enabled)


@router.post("/jobs")
async def create_job(request: JobCreateRequest):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    now = time.time()
    try:
        next_run = next_run_from_cron(request.cron, from_ts=now) if request.enabled else None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron: {e}")
    job = await store.create_job(
        {
            "name": request.name,
            "enabled": request.enabled,
            "cron": request.cron,
            "timezone": request.timezone,
            "kind": request.kind,
            "target_id": request.target_id,
            "user_id": request.user_id or "system",
            "session_id": request.session_id or "default",
            "payload": request.payload or {},
            "options": request.options or {},
            "delivery": request.delivery or {},
            "next_run_at": next_run,
        }
    )
    return job


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.put("/jobs/{job_id}")
async def update_job(job_id: str, request: JobUpdateRequest):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    patch = request.model_dump(exclude_unset=True)
    try:
        existing = await store.get_job(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Job not found")
        enabled = bool(patch.get("enabled")) if "enabled" in patch else bool(existing.get("enabled"))
        cron = str(patch.get("cron") or existing.get("cron") or "* * * * *")
        if enabled:
            patch["next_run_at"] = next_run_from_cron(cron, from_ts=time.time())
        else:
            patch["next_run_at"] = None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron: {e}")

    updated = await store.update_job(job_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return updated


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ok = await store.delete_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}


@router.post("/jobs/{job_id}/enable")
async def enable_job(job_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    next_run = next_run_from_cron(str(job.get("cron") or "* * * * *"), from_ts=time.time())
    updated = await store.update_job(job_id, {"enabled": True, "next_run_at": next_run})
    return updated


@router.post("/jobs/{job_id}/disable")
async def disable_job(job_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    updated = await store.update_job(job_id, {"enabled": False, "next_run_at": None})
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return updated


@router.post("/jobs/{job_id}/run")
async def run_job_now(job_id: str):
    scheduler = _scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="JobScheduler not running")
    try:
        return await scheduler.run_job_once(job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/jobs/{job_id}/runs/{run_id}")
async def get_job_run(job_id: str, run_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    run = await store.get_job_run(run_id)
    if not run or str(run.get("job_id")) != str(job_id):
        raise HTTPException(status_code=404, detail="Job run not found")
    return run


@router.get("/jobs/{job_id}/runs")
async def list_job_runs(job_id: str, limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_job_runs(job_id=job_id, limit=limit, offset=offset)


@router.get("/jobs/dlq")
async def list_job_delivery_dlq(status: Optional[str] = None, job_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_job_delivery_dlq(status=status, job_id=job_id, limit=limit, offset=offset)


@router.post("/jobs/dlq/{dlq_id}/retry")
async def retry_job_delivery_dlq(dlq_id: str):
    scheduler = _scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="JobScheduler not running")
    try:
        return await scheduler.retry_dlq_delivery(dlq_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/jobs/dlq/{dlq_id}")
async def delete_job_delivery_dlq(dlq_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ok = await store.delete_job_delivery_dlq_item(dlq_id)
    if not ok:
        raise HTTPException(status_code=404, detail="DLQ item not found")
    return {"status": "deleted", "dlq_id": dlq_id}

