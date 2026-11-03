"""Shared result envelope for eval runners (+ P1 scoring semantics)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.scoring.semantics import enrich_runner_result


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
    groundedness_dimension: Optional[Dict[str, Any]] = None,
    efficiency_dimension: Optional[Dict[str, Any]] = None,
    session_dimension: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw = {
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
    if groundedness_dimension is not None:
        raw["groundedness_dimension"] = groundedness_dimension
    if efficiency_dimension is not None:
        raw["efficiency_dimension"] = efficiency_dimension
    if session_dimension is not None:
        raw["session_dimension"] = session_dimension
    return enrich_runner_result(raw)
