"""
Comparative Evaluation — pairwise judge between current and baseline evaluation reports.

Answers: "Did this optimization round actually improve, or regress?"

Per §1.1: code lives in harness/evaluation — a core capability, not a team-specific one.
Delegates LLM calls to StageRunner (per §5.23).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CompareResult:
    """Result of comparing current vs baseline evaluation reports."""
    verdict: str = ""                    # "improved" | "flat" | "regressed"
    stop_recommendation: str = "continue"  # "continue" | "stop" | "review"
    improvement_headroom: str = "low"      # "none" | "low" | "medium" | "high"
    confidence: str = "medium"            # "low" | "medium" | "high"
    evidence_count: int = 1               # number of evaluation rounds this is based on
    uncertainty: str = "high"             # "low" | "medium" | "high" — epistemic uncertainty from insufficient evidence
    reason: str = ""
    dimension_details: Dict[str, str] = field(default_factory=dict)


def _derive_uncertainty(eval_count: int) -> str:
    """Derive epistemic uncertainty from the number of evaluation rounds.

    Bayesian intuition: 3 evaluations → high uncertainty (small sample).
    50 evaluations → low uncertainty (large sample). This is the
    subjective-logic dimension: same score change means different things
    depending on how many times we've observed it.
    """
    if eval_count < 3:
        return "high"
    if eval_count < 10:
        return "medium"
    return "low"


async def pairwise_judge(
    baseline: Dict[str, Any],
    current: Dict[str, Any],
    eval_count: int = 1,
) -> CompareResult:
    """
    Compare two evaluation reports using LLM.

    Args:
        baseline: The previous round's evaluation report (or first run's).
        current: The current round's evaluation report.

    Returns:
        CompareResult with verdict, stop recommendation, and improvement assessment.
    """
    # Quick check: no baseline means always "improved" (first run)
    if not baseline or not isinstance(baseline, dict) or not baseline:
        return CompareResult(
            verdict="improved",
            stop_recommendation="continue",
            improvement_headroom="high",
            confidence="low",
            evidence_count=eval_count,
            uncertainty=_derive_uncertainty(eval_count),
            reason="No baseline available — first evaluation round",
        )

    # Extract key metrics without LLM (fast path)
    bl_score = baseline.get("score") if isinstance(baseline.get("score"), dict) else {}
    cr_score = current.get("score") if isinstance(current.get("score"), dict) else {}
    bl_func = bl_score.get("functionality", 0)
    cr_func = cr_score.get("functionality", 0)
    bl_overall = bl_score.get("overall") or 0
    cr_overall = cr_score.get("overall") or 0
    bl_pass = baseline.get("pass")
    cr_pass = current.get("pass")
    bl_issues = len(baseline.get("issues") or [])
    cr_issues = len(current.get("issues") or [])

    # Local code: data-driven stop/continue signals (no LLM cost)
    func_improved = cr_func > bl_func + 0.5
    func_regressed = cr_func < bl_func - 1.0
    issues_reduced = cr_issues < bl_issues
    issues_worsened = cr_issues > bl_issues + 2

    # Derive stop recommendation from data
    if func_regressed:
        verdict = "regressed"
        stop_rec = "stop"
        headroom = "none"
        confidence = "high"
        reason = f"Functionality regressed from {bl_func:.1f} to {cr_func:.1f}"
    elif not func_improved and not issues_reduced:
        verdict = "flat"
        headroom = "low"
        if cr_pass and not func_regressed:
            stop_rec = "stop"  # flat + passing → good enough, stop
            reason = f"No improvement detected (func={cr_func:.1f}, issues={cr_issues}, pass={cr_pass})"
        else:
            stop_rec = "review"
            reason = f"No improvement but still failing — may need different approach"
        confidence = "medium"
    elif func_improved and cr_pass:
        verdict = "improved"
        headroom = "medium"
        stop_rec = "stop"  # improved + passing → success
        reason = f"Functionality improved from {bl_func:.1f} to {cr_func:.1f}, all passing"
        confidence = "high"
    else:
        verdict = "improved"
        headroom = "medium"
        stop_rec = "continue"
        reason = f"Functionality improved ({bl_func:.1f}→{cr_func:.1f}) but not yet passing — continue"
        confidence = "medium"

    return CompareResult(
        verdict=verdict,
        stop_recommendation=stop_rec,
        improvement_headroom=headroom,
        confidence=confidence,
        evidence_count=eval_count,
        uncertainty=_derive_uncertainty(eval_count),
        reason=reason,
        dimension_details={
            "functionality": "improved" if func_improved else ("regressed" if func_regressed else "flat"),
            "issues": "improved" if issues_reduced else ("worsened" if issues_worsened else "flat"),
            "overall": f"{bl_overall}→{cr_overall}",
        },
    )


def verify_prediction(
    prediction: Dict[str, Any],
    actual_delta: CompareResult,
) -> str:
    """
    Cross-round prediction verification (AHE-style).

    Args:
        prediction: The edit prediction from the version metadata
                    {predicted_fixes: [...], predicted_regressions: [...]}
        actual_delta: The actual CompareResult from running the version

    Returns:
        "confirmed" — predicted fixes happened, no predicted regressions triggered
        "partial"  — some predicted fixes happened OR some predicted regressions occurred
        "rolled_back" — predicted fixes didn't happen AND predicted regressions did
    """
    predicted_fixes = prediction.get("predicted_fixes") or []
    predicted_regressions = prediction.get("predicted_regressions") or []

    fixes_achieved = actual_delta.verdict == "improved"
    regressions_happened = actual_delta.verdict == "regressed"

    if fixes_achieved and not regressions_happened:
        if predicted_regressions:
            # Check if any predicted regressions actually occurred
            details = actual_delta.dimension_details or {}
            any_regression = any(v == "regressed" for v in details.values())
            if any_regression:
                return "partial"
        return "confirmed"
    elif not fixes_achieved and regressions_happened:
        return "rolled_back"
    else:
        return "partial"
