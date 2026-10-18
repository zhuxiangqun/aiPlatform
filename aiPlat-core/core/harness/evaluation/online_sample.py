"""Online eval sampling. Empty until a run is explicitly sampled.

Callers treat a missing or unavailable summary as "no invented pass rate".
"""

from __future__ import annotations

from typing import Any, Dict


def summarize_online_samples() -> Dict[str, Any]:
    return {"available": False, "sampled": 0, "metrics": {}}


def maybe_record_online_sample(context: Any) -> None:
    """No-op when sampling is not configured. Must not raise."""
    if not outcome_log_enabled() or not should_sample_run(""):
        return None
    return None


def should_sample_run(run_id: str = "") -> bool:
    return False


def outcome_log_enabled() -> bool:
    return False
