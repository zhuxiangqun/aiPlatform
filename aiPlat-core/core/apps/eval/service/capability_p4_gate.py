"""P4 gates — judge calibration report-only bar + benchmark readiness.

Never opens claim_eligible / accuracy_claim. ADR §6.2 agreement threshold
remains open; v1 always report-only even when engineering bar is met.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from core.apps.eval.service.capability_case_bank import (
    PACK_ID,
    PACK_VERSION,
    agent_benchmark_profile,
    build_agent_capability_cases,
)
from core.apps.eval.service.capability_coverage_fill import analyze_capability_coverage
from core.apps.eval.service.case_calibration import (
    CaseCalibrationError,
    compute_rating_agreement,
    create_judge_ticket,
    load_judge_ticket,
)
from core.apps.eval.service.suite_profile_compile import compile_plan_from_suite_profile

# Engineering bar only — does NOT unlock claim (ADR §6.2 still open).
DEFAULT_AGREEMENT_THRESHOLD = 0.8
BENCHMARK_MIN_PER_CAP = 8


class CapabilityP4GateError(ValueError):
    """P4 gate failure."""


def evaluate_judge_calibration_gate(
    *,
    agreement: Optional[Mapping[str, Any]] = None,
    ratings: Optional[Sequence[Mapping[str, Any]]] = None,
    threshold: float = DEFAULT_AGREEMENT_THRESHOLD,
    ticket: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute engineering agreement bar; always report-only for claim."""
    if agreement is None:
        if ratings is not None:
            agreement = compute_rating_agreement(ratings)
        elif ticket and isinstance(ticket.get("agreement"), Mapping):
            agreement = dict(ticket["agreement"])
        else:
            agreement = {
                "agreement": None,
                "pairs": 0,
                "n_cases": 0,
                "n_ratings": 0,
                "by_case": [],
                "calibrated": False,
                "accuracy_claim": False,
            }
    try:
        thr = float(threshold)
    except (TypeError, ValueError) as e:
        raise CapabilityP4GateError(f"threshold invalid: {threshold!r}") from e
    if thr <= 0 or thr > 1:
        raise CapabilityP4GateError("threshold must be in (0, 1]")

    raw = agreement.get("agreement") if isinstance(agreement, Mapping) else None
    score = float(raw) if raw is not None else None
    meets = bool(score is not None and score >= thr)
    ticket_status = str((ticket or {}).get("status") or "") if ticket else ""
    calibrated_eng = bool((ticket or {}).get("calibrated")) if ticket else False

    return {
        "ok": True,
        "schema": "eval.judge_calibration_gate.v1",
        "threshold": thr,
        "agreement": score,
        "agreement_detail": dict(agreement) if isinstance(agreement, Mapping) else {},
        "meets_engineering_bar": meets,
        "ticket_status": ticket_status or None,
        "engineering_calibrated": calibrated_eng,
        # Honesty locks — ADR open question #8: never unlock claim in v1.
        "report_only": True,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            "judge-human agreement is engineering-only; report_only=true; "
            "claim_eligible stays false until ADR §6.2 threshold is owner-approved"
        ),
    }


def open_capability_judge_calibration(
    *,
    workspace_id: str,
    pack_id: str = PACK_ID,
    version: str = PACK_VERSION,
    sample_n: int = 8,
    notes: str = "",
    caller_workspace_id: str = "",
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Open judge ticket sampling first N case_ids from capability bank."""
    bank = list(cases) if cases is not None else build_agent_capability_cases()
    ids = [str(c.get("case_id") or "") for c in bank if str(c.get("case_id") or "")]
    sample = ids[: max(1, int(sample_n))]
    try:
        ticket = create_judge_ticket(
            workspace_id=workspace_id,
            pack_id=pack_id or PACK_ID,
            version=version or PACK_VERSION,
            sample_case_ids=sample,
            notes=str(notes or "P4 capability bank judge calibration"),
            caller_workspace_id=caller_workspace_id or workspace_id,
        )
    except CaseCalibrationError as e:
        raise CapabilityP4GateError(str(e)) from e
    gate = evaluate_judge_calibration_gate(ticket=ticket)
    return {
        "ok": True,
        "ticket": ticket,
        "ticket_id": ticket.get("ticket_id"),
        "gate": gate,
        "sample_case_ids": sample,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": gate.get("honesty"),
    }


def judge_calibration_gate_for_ticket(
    *,
    workspace_id: str,
    ticket_id: str,
    threshold: float = DEFAULT_AGREEMENT_THRESHOLD,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Load ticket and evaluate engineering gate (claim still closed)."""
    try:
        ticket = load_judge_ticket(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            caller_workspace_id=caller_workspace_id or workspace_id,
        )
    except CaseCalibrationError as e:
        raise CapabilityP4GateError(str(e)) from e
    gate = evaluate_judge_calibration_gate(ticket=ticket, threshold=threshold)
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "ticket": ticket,
        "gate": gate,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": gate.get("honesty"),
    }


def benchmark_readiness_report(
    *,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    min_per_capability: int = BENCHMARK_MIN_PER_CAP,
    compile_plan: bool = True,
) -> Dict[str, Any]:
    """Coverage vs benchmark floor + optional compile with holdout disclosure."""
    bank = list(cases) if cases is not None else build_agent_capability_cases()
    profile = agent_benchmark_profile()
    coverage = analyze_capability_coverage(
        bank, profile=profile, min_per_capability=min_per_capability
    )
    plan = None
    if compile_plan:
        plan = compile_plan_from_suite_profile(profile=profile, cases=bank)
    ready = coverage.get("n_gaps", 1) == 0
    return {
        "ok": True,
        "schema": "eval.benchmark_readiness.v1",
        "profile_id": profile.get("profile_id"),
        "ready_for_benchmark_quotas": ready,
        "coverage": coverage,
        "plan": plan,
        "holdout": (plan or {}).get("suite_profile", {}).get("holdout") if plan else None,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            "benchmark readiness is coverage/holdout disclosure only; "
            "not an accuracy claim; not Certification; claim_eligible stays false"
        ),
    }
