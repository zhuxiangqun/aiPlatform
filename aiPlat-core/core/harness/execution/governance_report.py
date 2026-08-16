"""Governance Report — unified explainability / audit view of a pipeline run.

Ties together the decision trace (B), cost budget (C), hypothesis generator (D),
and root-cause chain (E) into a single human-readable report for governance
oversight, billing, and explainability.

This is a GENERIC engine capability — no business concepts; the report
references stage IDs and trace/cost signals only.

Callers:
- ``core.api.core_facade`` canonical re-export (governance/audit endpoint)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _build_explanation(decision_count: int, chain: List[Dict[str, Any]],
                       hypotheses: List[Dict[str, Any]], cost: Dict[str, Any]) -> str:
    parts = [
        f"pipeline has {decision_count} stages",
        f"cost ${cost['cost_used_usd']:.4f}" +
        (f" (budget ${cost['cost_budget_usd']:.4f})" if cost["cost_budget_usd"] else " (no budget set)"),
    ]
    if chain:
        parts.append("root-cause chain (deep→shallow): " + " → ".join(c["stage_id"] for c in chain))
    if hypotheses:
        top = hypotheses[0]
        if top.get("stage_id"):
            parts.append(f"max-error stage {top['stage_id']} (contribution {top['confidence']:.2f})")
        parts.append(f"top hypothesis: {top['hypothesis']}")
    return "; ".join(parts) + "."


def build_run_report(
    run_id: str,
    cost_used_usd: float = 0.0,
    cost_budget_usd: float = 0.0,
    failed_stage_ids: Optional[List[str]] = None,
    test_report: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a complete governance/explainability report for a pipeline run.

    Aggregates the decision trace, cost, root-cause chain, and hypotheses into
    one report. ``cost_used_usd`` / ``cost_budget_usd`` come from the pipeline
    state (passed in by the caller), since cost is tracked per-run there.
    """
    from core.harness.execution.decision_trace import get_trace, trace_root_cause_chain, locate_max_error_node
    from core.harness.execution.hypothesis_generator import generate_hypotheses
    from core.harness.execution.cost_budget import get_pricing

    trace = get_trace(run_id)
    decisions = trace.get("decisions", {})

    decision_list: List[Dict[str, Any]] = []
    for did, rec in sorted(decisions.items(), key=lambda x: x[1].get("stage_id", "")):
        decision_list.append({
            "stage_id": rec.get("stage_id"),
            "confidence": rec.get("confidence", 0.7),
            "error_contribution": rec.get("error_contribution"),
            "depends_on": [d.rsplit("_", 1)[-1] for d in rec.get("depends_on", [])],
        })

    chain = trace_root_cause_chain(run_id, failed_stage_ids)
    hypotheses = generate_hypotheses(run_id, failed_stage_ids, test_report)
    max_err = locate_max_error_node(run_id, failed_stage_ids)

    cost = {
        "cost_used_usd": round(float(cost_used_usd or 0.0), 6),
        "cost_budget_usd": round(float(cost_budget_usd or 0.0), 6),
        "over_budget": bool(cost_budget_usd and cost_used_usd >= cost_budget_usd),
        "priced_models": len(get_pricing()),
    }

    explanation = _build_explanation(len(decision_list), chain, hypotheses, cost)

    return {
        "run_id": run_id,
        "decisions": decision_list,
        "cost": cost,
        "failure_analysis": {
            "max_error_stage": max_err.get("stage_id"),
            "max_error_contribution": max_err.get("error_contribution", 0.0),
            "hypotheses": hypotheses,
            "root_cause_chain": chain,
        },
        "explanation": explanation,
    }
