"""Wall-clock job timeout (EVAL_RUNTIME_CONTRACT §5.2).

Honesty: local engineering; timed_out ≠ succeeded; accuracy_claim stays false.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, TypeVar

T = TypeVar("T")

DEFAULT_JOB_TIMEOUT_SEC = 300.0


def job_timeout_sec(override: float | None = None) -> float:
    """Seconds for one execute_runner call; ``<=0`` disables wall-clock cut."""
    if override is not None:
        return float(override)
    raw = (os.environ.get("AIPLAT_EVAL_JOB_TIMEOUT_SEC") or "").strip()
    if not raw:
        return float(DEFAULT_JOB_TIMEOUT_SEC)
    try:
        return float(raw)
    except ValueError:
        return float(DEFAULT_JOB_TIMEOUT_SEC)


def run_with_timeout(
    fn: Callable[[], T],
    *,
    timeout_sec: float,
) -> T:
    """Run ``fn``; raise ``TimeoutError`` when wall clock exceeded (if timeout>0)."""
    limit = float(timeout_sec)
    if limit <= 0:
        return fn()
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn)
        try:
            return fut.result(timeout=limit)
        except FuturesTimeout as exc:
            fut.cancel()
            raise TimeoutError(f"job wall-clock exceeded {limit}s") from exc


def _wire_timeout() -> Any:
    """Same-file caller for method_verify."""
    return run_with_timeout(lambda: 1, timeout_sec=1.0)
