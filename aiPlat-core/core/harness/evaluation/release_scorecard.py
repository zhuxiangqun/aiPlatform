"""Release scorecard.

Missing measurements stay unavailable. This module does not invent dimension
scores from an empty metrics dict.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


def metrics_from_duty_summary(summary: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(summary, Mapping):
        return {}
    raw = summary.get("release_metrics")
    return dict(raw) if isinstance(raw, dict) else {}


def metrics_from_faithfulness_values(values: Optional[List[Any]]) -> Dict[str, Any]:
    nums = []
    for val in values or []:
        try:
            if val is not None:
                nums.append(float(val))
        except (TypeError, ValueError):
            continue
    if not nums:
        return {}
    return {"faithfulness": sum(nums) / len(nums)}


def build_release_scorecard(metrics: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    data = dict(metrics or {})
    dims = {
        key: val
        for key, val in data.items()
        if isinstance(val, (int, float)) and not isinstance(val, bool)
    }
    return {
        "dims": dims,
        "overall": None,
        "status": "unavailable" if not dims else "watch",
        "failed": [],
        "unavailable": [] if dims else ["unmeasured"],
    }


def scorecard_to_duty_check(scorecard: Mapping[str, Any] | None) -> str:
    if not isinstance(scorecard, Mapping):
        return "unavailable"
    status = str(scorecard.get("status") or "unavailable")
    if status in ("go", "watch", "block", "unavailable"):
        return status
    return "unavailable"


def release_decision(
    scorecard: Mapping[str, Any] | None,
    profile: Optional[str] = None,
) -> Dict[str, Any]:
    view = scorecard if isinstance(scorecard, Mapping) else {}
    return {
        "mode": "advisory",
        "status": scorecard_to_duty_check(view),
        "profile": profile,
        "failed": list(view.get("failed") or []),
        "untested": [],
    }
