"""Hypothesis Generator — root-cause hypotheses from the decision trace graph.

Zero-LLM: derives structured root-cause hypotheses from trace signals
(confidence, error_contribution, dependency fan-out) produced by the
decision trace graph (B). This turns "where did it fail" (locate_max_error_node)
into "why did it fail" (hypotheses), feeding a targeted regenerate.

This is a GENERIC engine capability — no business concepts; hypotheses
reference stage IDs and trace signals only.

Callers:
- ``core.api.core_facade`` canonical re-export (fix flow)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_LOW_CONFIDENCE = 0.5


def _hypothesis_text(stage_id: str, rec: Dict[str, Any], failed_downstream: int,
                     total_downstream: int) -> str:
    conf = float(rec.get("confidence", 0.7))
    if conf < _LOW_CONFIDENCE:
        return (f"stage '{stage_id}' produced output with confidence only {conf:.2f} "
                f"(<{_LOW_CONFIDENCE}), likely incomplete or ambiguous, "
                f"causing {failed_downstream}/{total_downstream} downstream failures")
    if total_downstream > 1 and failed_downstream > 0:
        return (f"stage '{stage_id}' is the common upstream of {total_downstream} "
                f"downstream stages, {failed_downstream} of which failed; "
                f"failure propagated along dependencies")
    return (f"stage '{stage_id}' output propagated failure signals downstream "
            f"({failed_downstream}/{total_downstream})")


def _suggested_action(stage_id: str, rec: Dict[str, Any]) -> str:
    conf = float(rec.get("confidence", 0.7))
    if conf < _LOW_CONFIDENCE:
        return (f"regenerate stage '{stage_id}', asking it to complete its output, "
                f"clarify the interface contract and acceptance criteria "
                f"(rather than blindly re-running every downstream stage)")
    return (f"regenerate stage '{stage_id}' and cascade-refresh its direct downstream stages")


def generate_hypotheses(
    run_id: str,
    failed_stage_ids: Optional[List[str]] = None,
    test_report: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Generate ranked root-cause hypotheses for a failed pipeline run.

    Reuses :func:`decision_trace.locate_max_error_node` to find the max
    error-contribution node, then derives structured hypotheses from the
    trace signals. Returns a list ordered by error_contribution (desc).
    """
    from core.harness.execution.decision_trace import locate_max_error_node, get_trace

    max_err = locate_max_error_node(run_id, failed_stage_ids)
    trace = get_trace(run_id)
    decisions = trace.get("decisions", {})

    hypotheses: List[Dict[str, Any]] = []

    stage_id = max_err.get("stage_id")
    decision_id = max_err.get("decision_id")
    if stage_id and decision_id in decisions:
        rec = decisions[decision_id]
        failed_downstream = int(max_err.get("failed_downstream", 0))
        total_downstream = int(max_err.get("total_downstream", 0))
        hypotheses.append({
            "stage_id": stage_id,
            "hypothesis": _hypothesis_text(stage_id, rec, failed_downstream, total_downstream),
            "evidence": {
                "confidence": float(rec.get("confidence", 0.7)),
                "error_contribution": float(max_err.get("error_contribution", 0.0)),
                "failed_downstream": failed_downstream,
                "total_downstream": total_downstream,
            },
            "confidence": float(max_err.get("error_contribution", 0.0)),
            "suggested_action": _suggested_action(stage_id, rec),
        })

    # Secondary hypotheses: other low-confidence upstream nodes that are
    # implicated (transitively) but not the single max contributor.
    for did, rec in decisions.items():
        sid = rec.get("stage_id", "")
        conf = float(rec.get("confidence", 0.7))
        contribution = rec.get("error_contribution") or 0.0
        if sid == stage_id or sid in {h["stage_id"] for h in hypotheses}:
            continue
        if conf < _LOW_CONFIDENCE and contribution > 0:
            hypotheses.append({
                "stage_id": sid,
                "hypothesis": _hypothesis_text(sid, rec, 0, 0),
                "evidence": {"confidence": conf, "error_contribution": float(contribution)},
                "confidence": float(contribution),
                "suggested_action": _suggested_action(sid, rec),
            })

    hypotheses.sort(key=lambda h: h["confidence"], reverse=True)

    if test_report and not hypotheses:
        hypotheses.append({
            "stage_id": None,
            "hypothesis": "no upstream node in the decision trace — the test failure may stem from the requirement itself or the environment",
            "evidence": {"test_report": (test_report or "")[:200]},
            "confidence": 0.0,
            "suggested_action": "review the requirement description or the test environment configuration",
        })

    return hypotheses
