"""B2-L Worker claim / heartbeat / execute-once (allowlist runners).

Honesty: process_split_authorized=false; no core.harness; local deterministic runners.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.store.jobs import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    claim_next_job,
    heartbeat_job,
    update_job_status,
)
from app.worker.allowlist_guard import admit_job_for_execute
from app.worker.runners import execute_runner


def process_once(
    db_url: str,
    *,
    worker_id: str = "worker-local",
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Optional[Dict[str, Any]]:
    """Claim → allowlist → heartbeat → execute+collect → succeeded|failed|dead_letter."""
    job = claim_next_job(
        db_url,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        max_attempts=max_attempts,
    )
    if not job:
        return None

    ok, code, detail = admit_job_for_execute(job)
    if not ok:
        updated = update_job_status(
            db_url,
            job["job_id"],
            status="dead_letter",
            error_code=code,
            error_detail=detail,
            attempts=int(job.get("attempts") or 0),
        )
        return {
            **(updated or job),
            "admitted": False,
            "claimed": True,
            "executed": False,
            "process_split_authorized": False,
        }

    heartbeat_job(
        db_url,
        job["job_id"],
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )

    try:
        result = execute_runner(job)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("sandbox_required:"):
            err_code, err_detail = "sandbox_required", msg
        elif msg.startswith("runner_forbidden:"):
            err_code, err_detail = "runner_forbidden", msg
        else:
            err_code, err_detail = "failed", msg
        updated = update_job_status(
            db_url,
            job["job_id"],
            status="dead_letter" if err_code != "failed" else "failed",
            error_code=err_code,
            error_detail=err_detail,
        )
        return {
            **(updated or job),
            "admitted": True,
            "claimed": True,
            "executed": False,
            "process_split_authorized": False,
        }
    except Exception as exc:
        updated = update_job_status(
            db_url,
            job["job_id"],
            status="failed",
            error_code="failed",
            error_detail=str(exc)[:500],
        )
        return {
            **(updated or job),
            "admitted": True,
            "claimed": True,
            "executed": False,
            "process_split_authorized": False,
        }

    final_status = "succeeded" if result.get("ok") else "failed"
    updated = update_job_status(
        db_url,
        job["job_id"],
        status=final_status,
        error_code="" if result.get("ok") else str(result.get("detail") or "runner_failed")[:120],
        error_detail="" if result.get("ok") else str(result.get("detail") or "")[:500],
        result=result,
    )
    return {
        **(updated or job),
        "admitted": True,
        "claimed": True,
        "executed": True,
        "result": result,
        "process_split_authorized": False,
    }


def _wire_process_once(db_url: str) -> Optional[Dict[str, Any]]:
    """Same-file caller for method_verify."""
    return process_once(db_url, worker_id="w-verify")
