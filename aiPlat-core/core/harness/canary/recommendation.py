"""
Canary action recommendation (pure functions).

Goal: give operators a consistent next action without auto-executing destructive steps.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple


def recommend_action(report: Any) -> Tuple[str, str]:
    """
    Return (action, reason).

    action:
      - "block": should block rollout / require manual intervention
      - "investigate": requires investigation but may not be a hard block
      - "continue": no action needed
    """
    if not isinstance(report, dict):
        return ("investigate", "missing_report")

    # Hard signals
    reg = report.get("regression") if isinstance(report.get("regression"), dict) else None
    if isinstance(reg, dict) and bool(reg.get("is_regression")):
        reasons = reg.get("reasons")
        if isinstance(reasons, list) and reasons:
            return ("block", "regression_gate:" + ";".join([str(x) for x in reasons[:5]]))
        return ("block", "regression_gate")

    # P0 issues
    issues = report.get("issues")
    if isinstance(issues, list):
        for it in issues[:200]:
            if not isinstance(it, dict):
                continue
            sev = str(it.get("severity") or "").strip().upper()
            if sev == "P0":
                title = str(it.get("title") or "p0_issue").strip()
                return ("block", f"P0:{title}")

    # Fail but no strong signal -> investigate
    if report.get("pass") is False:
        return ("investigate", "report_failed_without_p0_or_regression")
    return ("continue", "pass")

