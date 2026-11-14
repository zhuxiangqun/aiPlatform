"""P5 pre-gate — Certification readiness checklist (claim closed).

Evaluates Plan §8.5 relative completeness for a Suite Profile.
Does **not** perform external audit. ``certification_eligible`` stays false.
``claim_eligible`` / ``accuracy_claim`` stay false.
Subject-aware: bank + in-scope + validate follow Profile Subject.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.capability_case_bank import (
    PACK_ID,
    PACK_VERSION,
    validate_capability_case,
)
from core.apps.eval.service.capability_coverage_fill import (
    analyze_capability_coverage,
    resolve_coverage_context,
)
from core.apps.eval.service.capability_p4_gate import (
    DEFAULT_AGREEMENT_THRESHOLD,
    evaluate_judge_calibration_gate,
)
from core.apps.eval.service.suite_profile_compile import compile_plan_from_suite_profile
from core.apps.eval.service.suite_profile_report import build_capability_heatmap


class CapabilityCertReadinessError(ValueError):
    """Certification readiness evaluation failure."""


def _oracle_ok(case: Mapping[str, Any]) -> bool:
    rubric = case.get("rubric") if isinstance(case.get("rubric"), Mapping) else {}
    oracle = case.get("oracle") if isinstance(case.get("oracle"), Mapping) else {}
    criteria = (
        case.get("success_criteria")
        if isinstance(case.get("success_criteria"), Mapping)
        else {}
    )
    if rubric.get("type") or oracle.get("type") or criteria:
        must = (
            rubric.get("must_contain")
            or rubric.get("must_contain_any")
            or criteria.get("must_contain")
            or criteria.get("must_contain_any")
        )
        if must or rubric.get("paths") or oracle or criteria.get("must_not_contain"):
            return True
        # typed rubric without must_contain still counts if type present
        return bool(rubric.get("type") or oracle.get("type"))
    if str(case.get("scripted_answer") or "").strip():
        return True
    return False


def _review_ok(case: Mapping[str, Any]) -> bool:
    rev = case.get("review") if isinstance(case.get("review"), Mapping) else {}
    st = str(rev.get("status") or "").strip().lower()
    return st in ("purpose_ok", "reviewed", "approved", "frozen")


def _validate_case_for_subject(case: Mapping[str, Any], subject_kind: str) -> List[str]:
    kind = str(subject_kind or "agent").strip().lower() or "agent"
    if kind == "agent":
        return list(validate_capability_case(case) or [])
    try:
        from core.apps.eval.service.subject_adapter import get_subject_adapter

        return list(get_subject_adapter(kind).validate_case(case) or [])
    except Exception as exc:  # noqa: BLE001 — surface as validation error
        return [f"subject_validate_unavailable:{exc}"]


def evaluate_certification_readiness(
    *,
    profile_id: str = "agent.benchmark.v1",
    profile: Optional[Mapping[str, Any]] = None,
    subject_kind: str = "",
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    pack_kind: str = "",
    pack_status: str = "",
    judge_agreement: Optional[Mapping[str, Any]] = None,
    judge_threshold: float = DEFAULT_AGREEMENT_THRESHOLD,
    compile_plan: bool = True,
) -> Dict[str, Any]:
    """Score §8.5 checklist relative to a Profile; never unlocks certification/claim.

    Args:
        profile_id: profile 标识。
        profile: profile 参数。
        subject_kind: subject_kind 参数。
        cases: 用例列表。
        pack_kind: pack_kind 参数。
        pack_status: pack_status 参数。
        judge_agreement: judge_agreement 参数。
        judge_threshold: judge_threshold 参数。
        compile_plan: compile_plan 参数。
    """
    try:
        bank, kind, prof = resolve_coverage_context(
            profile=profile,
            profile_id=str(profile_id or "").strip(),
            subject_kind=subject_kind,
            cases=cases,
        )
    except Exception as e:
        raise CapabilityCertReadinessError(str(e)) from e
    if prof is None:
        raise CapabilityCertReadinessError(
            f"profile not resolved: profile_id={profile_id!r}"
        )

    coverage = analyze_capability_coverage(
        bank,
        profile=prof,
        profile_id=str(prof.get("profile_id") or profile_id or ""),
        subject_kind=kind,
    )
    heatmap = build_capability_heatmap(
        cases=bank,
        profile=prof,
        profile_id=str(prof.get("profile_id") or profile_id or ""),
        subject_kind=kind,
    )
    in_scope = list(coverage.get("in_scope") or [])
    out_of_scope = list(coverage.get("out_of_scope") or [])

    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []

    # 1. all in-scope capabilities defined (present in map + quotas targeting them)
    gap_ids = {str(g.get("capability_id")) for g in coverage.get("gaps") or []}
    in_scope_defined = sorted(in_scope) == sorted(gap_ids)
    checks.append(
        {
            "id": "in_scope_defined",
            "ok": in_scope_defined,
            "detail": f"subject={kind} in_scope={len(in_scope)}",
        }
    )
    if not in_scope_defined:
        blockers.append("in_scope_capabilities_incomplete")

    # 2. min cases per capability (quota / coverage gaps)
    n_gaps = int(coverage.get("n_gaps") or 0)
    checks.append(
        {
            "id": "min_cases_per_capability",
            "ok": n_gaps == 0,
            "detail": f"n_gaps={n_gaps}",
        }
    )
    if n_gaps:
        blockers.append(f"capability_case_gaps={n_gaps}")

    # 3. every case has decidable oracle (rubric / success_criteria / scripted)
    oracle_bad = [str(c.get("case_id") or "") for c in bank if not _oracle_ok(c)]
    checks.append(
        {
            "id": "oracle_decidable",
            "ok": len(oracle_bad) == 0,
            "detail": f"missing_oracle={len(oracle_bad)}",
            "case_ids": oracle_bad[:20],
        }
    )
    if oracle_bad:
        blockers.append(f"oracle_missing={len(oracle_bad)}")

    # mechanical case validation (agent factory or Subject adapter)
    invalid = []
    for c in bank:
        errs = _validate_case_for_subject(c, kind)
        if errs:
            invalid.append({"case_id": c.get("case_id"), "errors": errs[:5]})
    checks.append(
        {
            "id": "mechanical_case_valid",
            "ok": len(invalid) == 0,
            "detail": f"invalid={len(invalid)}",
            "samples": invalid[:5],
        }
    )
    if invalid:
        blockers.append(f"mechanical_invalid={len(invalid)}")

    # 4. selected/bank cases purpose_ok or pack frozen+reviewed
    reviewed_n = sum(1 for c in bank if _review_ok(c))
    pack_kind_l = str(pack_kind or "").strip().lower()
    status = str(pack_status or "").strip().lower()
    pack_frozen_reviewed = pack_kind_l == "frozen" and status in (
        "active",
        "reviewed",
        "frozen",
    )
    review_ok = pack_frozen_reviewed or (len(bank) > 0 and reviewed_n == len(bank))
    checks.append(
        {
            "id": "frozen_or_purpose_ok",
            "ok": review_ok,
            "detail": (
                f"pack_kind={pack_kind_l or '—'} pack_status={status or '—'} "
                f"purpose_ok={reviewed_n}/{len(bank)}"
            ),
        }
    )
    if not review_ok:
        blockers.append("cases_not_fully_reviewed_or_pack_not_frozen")

    # 5. manifest covers quotas (compile)
    plan = None
    manifest_ok = False
    if compile_plan:
        plan = compile_plan_from_suite_profile(profile=prof, cases=bank)
        sel = plan.get("selection") if isinstance(plan.get("selection"), Mapping) else {}
        degraded = bool(sel.get("degraded"))
        manifest = plan.get("sample_manifest") or []
        manifest_ok = bool(manifest) and not degraded
        checks.append(
            {
                "id": "manifest_covers_quotas",
                "ok": manifest_ok,
                "detail": (
                    f"manifest_n={len(manifest)} degraded={degraded} "
                    f"profile_id={plan.get('profile_id')}"
                ),
            }
        )
        if not manifest_ok:
            blockers.append("manifest_shortfall_or_empty")
    else:
        checks.append(
            {
                "id": "manifest_covers_quotas",
                "ok": False,
                "detail": "compile_plan=false skipped",
            }
        )
        blockers.append("manifest_not_compiled")

    # 6. unknown listed for out-of-scope
    unknown = list(heatmap.get("unknown_capabilities") or [])
    unknown_ids = {u.get("capability_id") for u in unknown}
    unknown_ok = unknown_ids == set(out_of_scope)
    checks.append(
        {
            "id": "unknown_disclosed",
            "ok": unknown_ok,
            "detail": f"unknown_n={len(unknown)} out_of_scope={len(out_of_scope)}",
        }
    )
    if not unknown_ok:
        blockers.append("unknown_capabilities_not_disclosed")

    # 7. disclosure fields present on compiled plan
    disclosure_ok = False
    if plan:
        disclosure_ok = all(
            [
                plan.get("profile_id"),
                plan.get("manifest_hash"),
                plan.get("execution_fingerprint"),
                plan.get("claim_eligible") is False,
            ]
        )
    checks.append(
        {
            "id": "disclosure_fields",
            "ok": disclosure_ok,
            "detail": "profile_id/manifest_hash/execution_fingerprint/claim=false",
        }
    )
    if not disclosure_ok:
        blockers.append("disclosure_incomplete")

    # Judge engineering bar (optional input; never unlocks claim)
    judge_gate = evaluate_judge_calibration_gate(
        agreement=judge_agreement,
        threshold=judge_threshold,
    )
    checks.append(
        {
            "id": "judge_engineering_bar",
            "ok": bool(judge_gate.get("meets_engineering_bar")),
            "detail": (
                f"agreement={judge_gate.get('agreement')} "
                f"threshold={judge_gate.get('threshold')} report_only=true"
            ),
            "required_for_profile_complete": False,
        }
    )

    # Relative completeness = checklist 1–7 (judge optional)
    required = [c for c in checks if c.get("required_for_profile_complete", True)]
    profile_complete = all(bool(c.get("ok")) for c in required)

    snapshot = {
        "pack_id": str(prof.get("pack_id") or PACK_ID),
        "pack_version": str(prof.get("pack_version") or PACK_VERSION),
        "profile_id": prof.get("profile_id"),
        "subject_kind": kind,
        "manifest_hash": (plan or {}).get("manifest_hash"),
        "plan_id": (plan or {}).get("plan_id"),
        "execution_fingerprint": (plan or {}).get("execution_fingerprint"),
        "case_count": len(bank),
        "n_gaps": n_gaps,
    }

    return {
        "ok": True,
        "schema": "eval.certification_readiness.v1",
        "subject_kind": kind,
        "profile_id": prof.get("profile_id"),
        "profile_complete": profile_complete,
        # Always false: P5 external audit is out of band.
        "certification_eligible": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "checks": checks,
        "blockers": blockers,
        "snapshot": snapshot,
        "coverage": {
            "n_gaps": n_gaps,
            "covered_capabilities": coverage.get("covered_capabilities"),
            "total_in_scope": coverage.get("total_in_scope"),
            "subject_kind": kind,
        },
        "unknown_capabilities": sorted(out_of_scope),
        "judge_gate": judge_gate,
        "honesty": (
            f"profile_complete is relative to declared {kind} in-scope + quotas (§8.5); "
            "certification_eligible=false until external audit (P5 另立项); "
            "claim_eligible/accuracy_claim remain false"
        ),
    }
