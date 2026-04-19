"""
Auto-smoke scheduler.

On workspace resource changes (agent/skill/mcp), enqueue a background smoke_e2e job.

Design goals:
- Async: do not block create/update APIs
- Dedup: same resource within N seconds triggers at most once
- Observable: stored as Jobs/JobRuns + Audit log
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _autosmoke_enabled() -> bool:
    return _truthy(os.getenv("AIPLAT_AUTOSMOKE_ENABLED", "false"))


def _dedup_seconds() -> int:
    try:
        return int(os.getenv("AIPLAT_AUTOSMOKE_DEDUP_SECONDS", "600") or "600")
    except Exception:
        return 600


def _default_agent_model() -> str:
    return (os.getenv("AIPLAT_AUTOSMOKE_AGENT_MODEL") or os.getenv("AIPLAT_AGENT_MODEL") or "deepseek-reasoner").strip()


async def enqueue_autosmoke(
    *,
    execution_store: Any,
    job_scheduler: Any,
    resource_type: str,
    resource_id: str,
    tenant_id: str = "ops_smoke",
    actor_id: str = "admin",
    detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Enqueue an autosmoke job run for a resource.

    Returns:
      {"enqueued": bool, "job_id": str, "reason": str|None}
    """
    if not _autosmoke_enabled():
        return {"enqueued": False, "reason": "disabled"}
    if not execution_store or not job_scheduler:
        return {"enqueued": False, "reason": "not_initialized"}
    if not resource_type or not resource_id:
        return {"enqueued": False, "reason": "missing_resource"}

    job_id = f"autosmoke-{resource_type}:{resource_id}"
    now = time.time()

    # Create or update a dedicated job record for this resource.
    job = await execution_store.get_job(job_id)
    if job is None:
        # cron doesn't matter because we run it manually; keep disabled to avoid periodic executions.
        job = await execution_store.create_job(
            {
                "id": job_id,
                "name": f"AutoSmoke {resource_type} {resource_id}",
                "enabled": False,
                "cron": "0 0 1 1 *",
                "kind": "smoke_e2e",
                "target_id": "smoke_e2e",
                "user_id": actor_id,
                "session_id": tenant_id,
                "payload": {},
            }
        )

    # Dedup by job.last_run_at
    last_run_at = None
    try:
        last_run_at = float(job.get("last_run_at")) if job.get("last_run_at") is not None else None
    except Exception:
        last_run_at = None
    if last_run_at is not None and now - last_run_at < float(_dedup_seconds()):
        return {"enqueued": False, "job_id": job_id, "reason": "dedup"}

    payload = {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "agent_model": _default_agent_model(),
        "source": "autosmoke",
        "changed_resource": {"type": resource_type, "id": resource_id},
        "detail": detail or {},
    }
    await execution_store.update_job(job_id, {"user_id": actor_id, "session_id": tenant_id, "payload": payload})

    # Audit (best-effort)
    try:
        await execution_store.add_audit_log(
            action="autosmoke_enqueued",
            status="ok",
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            detail={"job_id": job_id, "payload": payload},
        )
    except Exception:
        pass

    # Async execution: run once in background so API returns immediately.
    async def _run_once():
        try:
            await job_scheduler.run_job_once(job_id)
        except Exception:
            # job_run will be marked failed by scheduler when possible; swallow here to keep loop alive
            return

    asyncio.create_task(_run_once(), name=f"autosmoke:{resource_type}:{resource_id}")
    return {"enqueued": True, "job_id": job_id, "reason": None}

