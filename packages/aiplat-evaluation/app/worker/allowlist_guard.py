"""Worker dual-point allowlist check (EVAL_RUNTIME_CONTRACT §3.1).

Forged / bypass INSERT jobs must still be rejected before execute.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.runner_allowlist import assert_runner_allowed_for_execute
from app.store.jobs import get_job, update_job_status


def admit_job_for_execute(job: Dict[str, Any]) -> Tuple[bool, str, str]:
    """Return (ok, error_code, detail). ok=False → do not execute."""
    rid = str(job.get("runner_id") or "")
    try:
        assert_runner_allowed_for_execute(rid)
        return True, "", ""
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("sandbox_required:"):
            return False, "sandbox_required", f"runner {rid} requires B3 sandbox"
        return False, "runner_forbidden", f"runner {rid} not on B2 allowlist"


def reject_forged_job(db_url: str, job_id: str) -> Optional[Dict[str, Any]]:
    """Load job, re-check allowlist; on deny mark dead_letter + error codes."""
    job = get_job(db_url, job_id)
    if not job:
        return None
    ok, code, detail = admit_job_for_execute(job)
    if ok:
        return {**job, "admitted": True, "process_split_authorized": False}
    updated = update_job_status(
        db_url,
        job_id,
        status="dead_letter",
        error_code=code,
        error_detail=detail,
        attempts=int(job.get("attempts") or 0) + 1,
    )
    return {
        **(updated or job),
        "admitted": False,
        "process_split_authorized": False,
    }


def _wire_admit() -> Tuple[bool, str, str]:
    """Same-file caller for method_verify."""
    return admit_job_for_execute({"runner_id": "skill_suite"})
