"""B2-L Worker claim / heartbeat / one-shot process (lease before execute).

Honesty: process_split_authorized=false; execute runners land in a later slice.
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


def process_once(
    db_url: str,
    *,
    worker_id: str = "worker-local",
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Optional[Dict[str, Any]]:
    """Claim one job, dual-point allowlist, heartbeat; no runner execute yet.

    Returns None if queue empty. Denied jobs → dead_letter. Admitted jobs stay
    ``running`` under lease (execute plane next B2-L slice).
    """
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
            "process_split_authorized": False,
        }

    hb = heartbeat_job(
        db_url,
        job["job_id"],
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    return {
        **(hb or job),
        "admitted": True,
        "claimed": True,
        "process_split_authorized": False,
        "note": "B2-L claimed+leased; runner execute deferred",
    }


def _wire_process_once(db_url: str) -> Optional[Dict[str, Any]]:
    """Same-file caller for method_verify."""
    return process_once(db_url, worker_id="w-verify")
