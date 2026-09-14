"""Deterministic security_report assembler — Phase B (no LLM)."""

from __future__ import annotations

from typing import Any, Dict, List


def _artifact(params: Dict[str, Any], key: str) -> Dict[str, Any]:
    v = params.get(key)
    return v if isinstance(v, dict) else {}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    plan = _artifact(params, "security_plan")
    trace = _artifact(params, "security_trace")
    critique = _artifact(params, "security_critique")

    findings: List[Any] = list(critique.get("findings") or [])
    refuted: List[Any] = list(critique.get("refuted") or [])

    # Never escalate
    for f in findings:
        if isinstance(f, dict):
            f["severity"] = "candidate"
            f["heuristic"] = True

    header = {
        "phase": "B",
        "schema_version": plan.get("schema_version") or "secview.v1",
        "heuristic": True,
        "max_severity": "candidate",
        "token_baseline": {
            "plan_token_estimate": plan.get("_token_estimate"),
            "plan_chars": plan.get("_chars"),
            "digest_token_estimate": (plan.get("metrics") or {}).get("digest_token_estimate"),
        },
        "counts": {
            "hot_paths_selected": len(plan.get("top_hot_paths") or []),
            "traces": len(trace.get("traces") or []),
            "findings": len(findings),
            "refuted": len(refuted),
        },
        "disclaimer": (
            "call/import reachability ≠ taint; confirmed requires Phase C sandbox"
        ),
        "params": plan.get("params") or {},
    }

    return {
        "header": header,
        "findings": findings,
        "refuted": refuted,
        "next": "optional Phase C evidence for selected candidates",
        "notes": ["Phase B security_report handler — assembly only, no LLM"],
    }
