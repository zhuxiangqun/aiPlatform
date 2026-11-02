"""Shared result envelope for B2-L runners."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runner_result(
    *,
    runner_id: str,
    job_id: str,
    ok: bool,
    metrics: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    detail: str = "",
    mode: str = "local_deterministic",
) -> Dict[str, Any]:
    return {
        "ok": bool(ok),
        "runner_id": runner_id,
        "job_id": job_id,
        "metrics": metrics or {},
        "evidence": evidence or {},
        "detail": detail,
        "mode": mode,
        "collected_at": _now(),
        "process_split_authorized": False,
        "accuracy_claim": False,
    }
