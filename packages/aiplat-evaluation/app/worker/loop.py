"""B2-L Worker poll loop — process_once until idle/stop/max_jobs.

Honesty: environment=local engineering; process_split_authorized stays false.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.store.jobs import DEFAULT_LEASE_SECONDS, DEFAULT_MAX_ATTEMPTS
from app.worker.claim import process_once


@dataclass
class WorkerLoopResult:
    processed: int = 0
    idle_rounds: int = 0
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    stopped_reason: str = ""
    process_split_authorized: bool = False


def run_worker_loop(
    db_url: str,
    *,
    worker_id: str = "worker-local",
    idle_sleep_s: float = 0.5,
    max_jobs: Optional[int] = None,
    max_idle_rounds: Optional[int] = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    should_stop: Optional[Callable[[], bool]] = None,
    process_fn: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
) -> WorkerLoopResult:
    """Poll the job queue; stop on should_stop, max_jobs, or max_idle_rounds.

    When ``max_idle_rounds`` is None and ``max_jobs`` is None, loops until
    ``should_stop`` returns True (daemon mode). Tests pass finite limits.
    """
    fn = process_fn or process_once
    out = WorkerLoopResult()
    while True:
        if should_stop and should_stop():
            out.stopped_reason = "should_stop"
            break
        if max_jobs is not None and out.processed >= int(max_jobs):
            out.stopped_reason = "max_jobs"
            break

        job = fn(
            db_url,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )
        if job is None:
            out.idle_rounds += 1
            if max_idle_rounds is not None and out.idle_rounds >= int(max_idle_rounds):
                out.stopped_reason = "max_idle_rounds"
                break
            if idle_sleep_s > 0:
                time.sleep(float(idle_sleep_s))
            continue

        out.idle_rounds = 0
        out.processed += 1
        out.outcomes.append(
            {
                "job_id": job.get("job_id"),
                "runner_id": job.get("runner_id"),
                "status": job.get("status"),
                "admitted": job.get("admitted"),
                "executed": job.get("executed"),
            }
        )
    if not out.stopped_reason:
        out.stopped_reason = "exit"
    return out


def load_worker_env() -> Dict[str, Any]:
    """Read AIPLAT_EVAL_WORKER_* knobs (defaults safe for local)."""
    def _float(name: str, default: float) -> float:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def _int_opt(name: str) -> Optional[int]:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    return {
        "worker_id": (os.getenv("AIPLAT_EVAL_WORKER_ID") or "worker-local").strip()
        or "worker-local",
        "idle_sleep_s": _float("AIPLAT_EVAL_WORKER_IDLE_SLEEP", 0.5),
        "max_jobs": _int_opt("AIPLAT_EVAL_WORKER_MAX_JOBS"),
        "max_idle_rounds": _int_opt("AIPLAT_EVAL_WORKER_MAX_IDLE"),
        "lease_seconds": int(_float("AIPLAT_EVAL_WORKER_LEASE_SECONDS", float(DEFAULT_LEASE_SECONDS))),
        "max_attempts": int(_float("AIPLAT_EVAL_WORKER_MAX_ATTEMPTS", float(DEFAULT_MAX_ATTEMPTS))),
    }


def _wire_loop(db_url: str) -> WorkerLoopResult:
    """Same-file caller for method_verify."""
    return run_worker_loop(db_url, max_jobs=0, max_idle_rounds=1, idle_sleep_s=0)
