"""B2-L Worker claim / heartbeat / execute-once (allowlist runners).

Honesty: process_split_authorized=false; no core.harness; local deterministic runners.
Wall-clock exceed → status timed_out (never succeeded).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.store.jobs import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    claim_next_job,
    get_job,
    heartbeat_job,
    update_job_status,
)
from app.worker.allowlist_guard import admit_job_for_execute
from app.worker.runners import execute_runner
from app.worker.timeout import job_timeout_sec, run_with_timeout


def process_once(
    db_url: str,
    *,
    worker_id: str = "worker-local",
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    job_timeout_sec_override: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Claim → allowlist → heartbeat → execute+collect → succeeded|failed|dead_letter|timed_out."""
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

    timeout = job_timeout_sec(job_timeout_sec_override)
    try:
        result = run_with_timeout(lambda: execute_runner(job), timeout_sec=timeout)
    except TimeoutError as exc:
        updated = _write_unless_cancelled(
            db_url,
            job["job_id"],
            status="timed_out",
            error_code="timed_out",
            error_detail=str(exc)[:500],
            result={
                "ok": False,
                "accuracy_claim": False,
                "process_split_authorized": False,
                "detail": "timed_out",
                "timeout_sec": timeout,
            },
        )
        return {
            **(updated or job),
            "admitted": True,
            "claimed": True,
            "executed": False,
            "timed_out": updated.get("status") == "timed_out" if updated else True,
            "cancelled": (updated or {}).get("status") == "cancelled",
            "process_split_authorized": False,
        }
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("sandbox_required:"):
            err_code, err_detail = "sandbox_required", msg
        elif msg.startswith("runner_forbidden:"):
            err_code, err_detail = "runner_forbidden", msg
        else:
            err_code, err_detail = "failed", msg
        updated = _write_unless_cancelled(
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
            "cancelled": (updated or {}).get("status") == "cancelled",
            "process_split_authorized": False,
        }
    except Exception as exc:
        updated = _write_unless_cancelled(
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
            "cancelled": (updated or {}).get("status") == "cancelled",
            "process_split_authorized": False,
        }

    final_status = "succeeded" if result.get("ok") else "failed"
    updated = _write_unless_cancelled(
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
        "executed": (updated or {}).get("status") != "cancelled",
        "result": result,
        "cancelled": (updated or {}).get("status") == "cancelled",
        "process_split_authorized": False,
    }


def _write_unless_cancelled(
    db_url: str,
    job_id: str,
    *,
    status: str,
    error_code: str = "",
    error_detail: str = "",
    result: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Do not overwrite a cooperative cancel with succeeded/failed/timed_out."""
    current = get_job(db_url, job_id)
    if current and str(current.get("status") or "") == "cancelled":
        return current
    return update_job_status(
        db_url,
        job_id,
        status=status,
        error_code=error_code,
        error_detail=error_detail,
        result=result,
    )


def _wire_process_once(db_url: str) -> Optional[Dict[str, Any]]:
    """Same-file caller for method_verify."""
    return process_once(db_url, worker_id="w-verify")
