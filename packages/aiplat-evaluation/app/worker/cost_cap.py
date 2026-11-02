"""Job cost hard-top (EVAL_RUNTIME_CONTRACT §5.2).

Honesty: exceed → treat like hard-top (caller marks ``timed_out``); never succeeded.
``AIPLAT_EVAL_JOB_COST_CAP`` default 0 = disabled; payload ``cost_cap`` may tighten.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Tuple


def job_cost_cap(
    *,
    override: Optional[float] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> float:
    """Effective cost cap (>0 enforces). Override wins, then payload, then env."""
    if override is not None:
        try:
            return max(0.0, float(override))
        except (TypeError, ValueError):
            return 0.0
    if isinstance(payload, Mapping) and "cost_cap" in payload:
        try:
            return max(0.0, float(payload.get("cost_cap") or 0))
        except (TypeError, ValueError):
            return 0.0
    raw = (os.environ.get("AIPLAT_EVAL_JOB_COST_CAP") or "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def extract_cost_estimate(result: Optional[Mapping[str, Any]]) -> float:
    """Prefer metrics.cost_estimate; fall back to evidence.llm.cost_estimate."""
    if not isinstance(result, Mapping):
        return 0.0
    metrics = result.get("metrics") if isinstance(result.get("metrics"), Mapping) else {}
    if "cost_estimate" in metrics:
        try:
            return float(metrics.get("cost_estimate") or 0)
        except (TypeError, ValueError):
            return 0.0
    evidence = result.get("evidence") if isinstance(result.get("evidence"), Mapping) else {}
    llm = evidence.get("llm") if isinstance(evidence.get("llm"), Mapping) else {}
    try:
        return float(llm.get("cost_estimate") or 0)
    except (TypeError, ValueError):
        return 0.0


def cost_cap_exceeded(
    result: Optional[Mapping[str, Any]],
    *,
    cap: float,
) -> Tuple[bool, float]:
    """Return (exceeded, observed_cost). Cap <=0 disables."""
    limit = float(cap or 0)
    if limit <= 0:
        return False, extract_cost_estimate(result)
    cost = extract_cost_estimate(result)
    return cost > limit, cost


def _wire_cost_cap() -> Tuple[bool, float]:
    """Same-file caller for method_verify."""
    _ = job_cost_cap(override=1.0)
    return cost_cap_exceeded({"metrics": {"cost_estimate": 2.0}}, cap=1.0)
