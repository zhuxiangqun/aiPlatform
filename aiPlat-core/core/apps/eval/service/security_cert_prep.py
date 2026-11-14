"""CERT-PREP: certification preparation track (≠ security_certification).

Order (scheme follow-on):
  1) per-family scored harness → report_only vs L5-candidate
  2) judge calib evidence pack + G2b-S dual-review workflow
  3) limited L5 claim *rehearsal* (template + claims_gate; cert stays false)

Hard locks:
  - accuracy_claim / security_certification / claim_eligible always false here
  - explicit_authorize alone never flips certification
  - engineering_ready ≠ emitted L5 declaration ≠ certification
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.claims_gate import evaluate_l5_claims_gate
from core.apps.eval.service.g2b import g2b_l5_gap_disclosure, g2b_pack_status
from core.apps.eval.service.security_family_report import (
    build_security_family_report,
    evaluate_security_family_gates,
    load_l1_safety_cases_from_seed,
)
from core.apps.eval.service.security_judge_calib import (
    ASR_CALIBRATED,
    ASR_UNCALIBRATED,
    evaluate_security_judge_calibration,
    load_judge_calib_defaults,
)
from core.apps.eval.service.security_l5_claim_template import (
    build_security_l5_claim_template,
)

STATUS_SCHEMA = "eval.security_cert_prep_status.v1"
FAMILY_RUN_SCHEMA = "eval.security_cert_prep_family_run.v1"
JUDGE_PACK_SCHEMA = "eval.security_cert_prep_judge_evidence.v1"
G2B_WF_SCHEMA = "eval.security_cert_prep_g2b_s_workflow.v1"
REHEARSAL_SCHEMA = "eval.security_cert_prep_l5_rehearsal.v1"


class SecurityCertPrepError(ValueError):
    """Fail-closed CERT-PREP error."""


def _locks() -> Dict[str, Any]:
    return {
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
    }


def run_per_family_cert_prep(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    subject: Optional[Mapping[str, Any]] = None,
    pack_id: str = "agent.safety.cert_prep",
    eval_layer: str = "L1",
    use_seed_annotation_fixture: bool = False,
) -> Dict[str, Any]:
    """Per-family harness: classify L5-candidate vs report_only vs untested.

    Args:
        by_case: by_case 参数。
        subject: subject 参数。
        pack_id: pack 标识。
        eval_layer: eval_layer 参数。
        use_seed_annotation_fixture: use_seed_annotation_fixture 参数。
    """
    cases = dict(by_case or {})
    annotation_only = False
    if not cases and use_seed_annotation_fixture:
        annotation_only = True
        seed = load_l1_safety_cases_from_seed()
        for c in seed:
            cid = str(c.get("case_id") or "")
            if not cid:
                continue
            cases[cid] = {
                "threat_ids": list(c.get("threat_ids") or []),
                "ok": True,
                "annotation_only": True,
            }

    report = build_security_family_report(
        by_case=cases,
        subject=subject,
        pack_id=pack_id,
        eval_layer=eval_layer,
    )
    if annotation_only:
        report["annotation_only"] = True
        for b in (report.get("families") or {}).values():
            if isinstance(b, dict) and int(b.get("n") or 0) > 0:
                b["status"] = "annotated_l1"
                b["rate"] = None
                b["note"] = "annotation_only_not_scored_run"
        # Recompute gates without treating annotation as engineering_ready.
        gates = {
            "schema": "eval.security_family_gates.v1",
            "below_min_n_families": [],
            "engineering_ready_families": [],
            "report_only_families": [],
            "untested_families": list(report.get("untested_threat_families") or []),
            "annotated_families": sorted(
                fid
                for fid, row in (report.get("families") or {}).items()
                if isinstance(row, Mapping) and str(row.get("status")) == "annotated_l1"
            ),
            "l5_declare_allowed_families": [],
            **_locks(),
            "honesty": "Annotation fixture ≠ scored CERT-PREP run.",
        }
    else:
        gates = evaluate_security_family_gates(report)

    ready = list(gates.get("engineering_ready_families") or [])
    report_only = list(gates.get("report_only_families") or gates.get("below_min_n_families") or [])
    untested = list(gates.get("untested_families") or report.get("untested_threat_families") or [])

    return {
        "schema": FAMILY_RUN_SCHEMA,
        "ok": True,
        "annotation_only": annotation_only,
        "n_cases": len(cases),
        "family_report": report,
        "family_gates": gates,
        "l5_candidate_families": ready if not annotation_only else [],
        "report_only_families": report_only if not annotation_only else [],
        "untested_families": untested,
        "l5_declare_allowed_families": [],
        **_locks(),
        "honesty": (
            "CERT-PREP per-family classification only. "
            "engineering_ready → L5-candidate set; never auto-declare or certify."
        ),
    }


def build_judge_calib_evidence_pack(
    *,
    judge_model: str = "eval-judge-model",
    subject_model: str = "prod-subject-model",
    judge_id: str = "security.policy_judge",
    judge_version: str = "1.0.0",
    pairs: Optional[Sequence[Mapping[str, Any]]] = None,
    dual_human_completed: bool = False,
    failure_case_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Package judge isolation + calibration report for CERT-PREP evidence.

    Args:
        judge_model: 裁判模型。
        subject_model: 被测模型。
        judge_id: judge 标识。
        judge_version: judge_version 参数。
        pairs: 对照样本序列。
        dual_human_completed: dual_human_completed 参数。
        failure_case_ids: failure_case_ids 参数。
    """
    defaults = load_judge_calib_defaults()
    pair_rows = [dict(x) for x in (pairs or []) if isinstance(x, Mapping)]
    fail_ids = [str(x) for x in (failure_case_ids or []) if str(x).strip()]
    manifest = {
        "schema": "eval.security_judge_version_manifest.v1",
        "judge_id": judge_id,
        "judge_version": judge_version,
        "judge_model": judge_model,
        "subject_model": subject_model,
        "dual_human_completed": bool(dual_human_completed),
    }
    report = evaluate_security_judge_calibration(
        pairs=pair_rows,
        defaults=defaults,
        manifest=manifest,
        dual_human_on_failures=True if fail_ids else False,
        failure_case_ids=fail_ids,
    )
    asr_status = str(report.get("asr_status") or ASR_UNCALIBRATED)
    usable = bool(report.get("meets_engineering_bar")) and asr_status == ASR_CALIBRATED
    return {
        "schema": JUDGE_PACK_SCHEMA,
        "ok": True,
        "defaults_version": defaults.get("version"),
        "manifest": manifest,
        "calibration_report": report,
        "judge_usable_for_l5_candidate": usable,
        "asr_calibration_status": asr_status,
        **_locks(),
        "honesty": (
            "Judge evidence pack for CERT-PREP. "
            "Uncalibrated / self-judge → not L5-candidate usable."
        ),
    }


def build_g2b_s_dual_review_workflow(
    *,
    tenant_id: str = "eval-v1",
    security_failure_ids: Optional[Sequence[str]] = None,
    dual_reviews: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """G2b-S dual-blind review checklist for CERT-PREP (facilitation).

    Args:
        tenant_id: 租户 ID。
        security_failure_ids: security_failure_ids 参数。
        dual_reviews: dual_reviews 参数。
    """
    pack = g2b_pack_status(tenant_id=tenant_id)
    gap = g2b_l5_gap_disclosure(tenant_id=tenant_id)
    fails = [str(x) for x in (security_failure_ids or []) if str(x).strip()]
    reviews = dict(dual_reviews or {})

    pending: List[str] = []
    completed: List[str] = []
    for fid in fails:
        row = reviews.get(fid) if isinstance(reviews.get(fid), Mapping) else {}
        r1 = str(row.get("reviewer_a") or "").strip()
        r2 = str(row.get("reviewer_b") or "").strip()
        independent = bool(row.get("independent_blind"))
        if r1 and r2 and r1 != r2 and independent:
            completed.append(fid)
        else:
            pending.append(fid)

    all_failures_dual = (not fails) or (not pending)
    return {
        "schema": G2B_WF_SCHEMA,
        "ok": True,
        "g2b_pack": {
            "pack_ready": pack.get("pack_ready"),
            "target_n": pack.get("target_n"),
            "pending_dual_human": pack.get("pending_dual_human"),
            "dual_human_complete": pack.get("dual_human_complete"),
        },
        "g2b_l5_gaps": gap.get("gaps") or [],
        "security_failures": fails,
        "dual_review_completed_ids": completed,
        "dual_review_pending_ids": pending,
        "all_security_failures_dual_reviewed": all_failures_dual,
        "arbiter_required_on_disagreement": True,
        "ready_for_l5_rehearsal": bool(
            all_failures_dual and pack.get("dual_human_complete")
        ),
        **_locks(),
        "honesty": (
            "G2b-S workflow facilitation. Pack closeout + failure dual-blind "
            "required before L5 rehearsal can be 'ready'; never certification."
        ),
    }


def rehearse_l5_limited_claim(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    subject: Optional[Mapping[str, Any]] = None,
    pack_id: str = "agent.safety.cert_prep",
    pack_version: str = "0.0.0-rehearsal",
    runtime_tier: str = "workspace_execute",
    judge_id: str = "security.policy_judge",
    judge_version: str = "1.0.0",
    asr_calibration_status: str = ASR_UNCALIBRATED,
    judge_usable: bool = False,
    explicit_authorize: bool = False,
    signoffs: Optional[Mapping[str, Any]] = None,
    sample_n: int = 0,
    has_run_evidence: bool = False,
    human_review: bool = False,
) -> Dict[str, Any]:
    """Rehearse limited L5 claim template + claims_gate. Cert always false.

    Args:
        by_case: by_case 参数。
        subject: subject 参数。
        pack_id: pack 标识。
        pack_version: pack_version 参数。
        runtime_tier: runtime_tier 参数。
        judge_id: judge 标识。
        judge_version: judge_version 参数。
        asr_calibration_status: asr_calibration_status 参数。
        judge_usable: judge_usable 参数。
        explicit_authorize: explicit_authorize 参数。
        signoffs: signoffs 参数。
        sample_n: sample_n 参数。
        has_run_evidence: 布尔开关。
        human_review: human_review 参数。
    """
    tmpl = build_security_l5_claim_template(
        by_case=by_case or {},
        subject=subject or {"label": "cert-prep-subject", "object_id": "cert-prep"},
        pack_id=pack_id,
        pack_version=pack_version,
        runtime_tier=runtime_tier,
        judge_id=judge_id,
        judge_version=judge_version,
        asr_calibration_status=asr_calibration_status,
        judge_usable=judge_usable,
        explicit_authorize=explicit_authorize,
        signoffs=signoffs,
    )
    candidates = list(tmpl.get("declare_candidate_families") or [])
    untested_n = len(tmpl.get("untested_threat_families") or []) + len(
        tmpl.get("below_min_n_families") or []
    )
    gate = evaluate_l5_claims_gate(
        {
            "object_type": "agent",
            "object_id": str((subject or {}).get("object_id") or "cert-prep"),
            "object_version": pack_version,
            "runtime_tier": runtime_tier,
            "plan_id": "security_cert_prep",
            "set_ids": candidates or ["none"],
            "oracle_types": ["security_family"],
            "dimensions": ["threat_family_asr"],
            "sample_n": int(sample_n),
            "has_run_evidence": bool(has_run_evidence),
            "untested_applicable_n": int(untested_n),
            "runtime_claim": bool(has_run_evidence),
            "fixture_only": runtime_tier == "fixture",
            "human_review": bool(human_review),
            "claim_eligible": False,  # CERT-PREP rehearsal never pack-claim-eligible
            "min_sample_n": 100,
        },
        explicit_authorize=bool(explicit_authorize),
    )
    # Absolute hard lock for this track
    gate = dict(gate)
    gate["accuracy_claim"] = False
    gate["sufficiency_claim"] = False
    gate["security_certification"] = False

    return {
        "schema": REHEARSAL_SCHEMA,
        "ok": True,
        "template": tmpl,
        "claims_gate": gate,
        "rehearsal_only": True,
        "l5_declare_emitted": False,
        "authorize_requested": bool(explicit_authorize),
        "blockers": list(tmpl.get("blockers") or [])
        + list(gate.get("failed") or [])
        + list(gate.get("missing") or []),
        **_locks(),
        "honesty": (
            "CERT-PREP L5 rehearsal only. "
            "Even with explicit_authorize, security_certification stays false; "
            "requires tripartite live sign-off outside this engineering track."
        ),
    }


def security_cert_prep_status(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    subject: Optional[Mapping[str, Any]] = None,
    judge_model: str = "eval-judge-model",
    subject_model: str = "prod-subject-model",
    security_failure_ids: Optional[Sequence[str]] = None,
    dual_reviews: Optional[Mapping[str, Mapping[str, Any]]] = None,
    explicit_authorize: bool = False,
    signoffs: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Facade-friendly CERT-PREP dashboard across the three prep steps.

    Args:
        by_case: by_case 参数。
        subject: subject 参数。
        judge_model: 裁判模型。
        subject_model: 被测模型。
        security_failure_ids: security_failure_ids 参数。
        dual_reviews: dual_reviews 参数。
        explicit_authorize: explicit_authorize 参数。
        signoffs: signoffs 参数。
    """
    family = run_per_family_cert_prep(
        by_case=by_case,
        subject=subject,
        use_seed_annotation_fixture=not bool(by_case),
    )
    judge = build_judge_calib_evidence_pack(
        judge_model=judge_model,
        subject_model=subject_model,
    )
    g2b = build_g2b_s_dual_review_workflow(
        security_failure_ids=security_failure_ids,
        dual_reviews=dual_reviews,
    )
    rehearsal = rehearse_l5_limited_claim(
        by_case=by_case or {},
        subject=subject,
        asr_calibration_status=str(judge.get("asr_calibration_status") or ASR_UNCALIBRATED),
        judge_usable=bool(judge.get("judge_usable_for_l5_candidate")),
        explicit_authorize=explicit_authorize,
        signoffs=signoffs,
        has_run_evidence=bool(by_case),
        sample_n=int(family.get("n_cases") or 0),
        human_review=bool(g2b.get("all_security_failures_dual_reviewed")),
    )
    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "slice": "CERT-PREP",
        "per_family": family,
        "judge_evidence": judge,
        "g2b_s_workflow": g2b,
        "l5_rehearsal": rehearsal,
        "next_human_gates": [
            "score_live_per_family_runs",
            "freeze_judge_version_and_meet_calib_thresholds",
            "complete_g2b_s_dual_blind_on_all_failures",
            "triple_signoff_then_manual_claims_gate_outside_auto_path",
        ],
        **_locks(),
        "honesty": (
            "CERT-PREP engineering track complete as facilitation. "
            "≠ security_certification / accuracy_claim."
        ),
    }
