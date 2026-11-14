"""Suite Profile exam report — coverage heatmap + honesty disclosure.

Builds the §8.4 coverage table and §11 disclosure block from a Profile exam
result (and optional bank/coverage analysis). Never opens claim_eligible.
Subject-aware: in-scope rows follow the Profile Subject catalog.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.capability_coverage_fill import (
    analyze_capability_coverage,
    resolve_coverage_context,
    subject_capability_scope,
)


def _cap_of_case(case: Mapping[str, Any]) -> str:
    caps = case.get("capabilities") or []
    if caps:
        return str(caps[0])
    return str(case.get("category") or "").strip()


def build_capability_heatmap(
    *,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    exam: Optional[Mapping[str, Any]] = None,
    profile: Optional[Mapping[str, Any]] = None,
    profile_id: str = "",
    subject_kind: str = "",
) -> Dict[str, Any]:
    """§8.4 coverage heatmap: capability → bank/selected/pass/fail/gap/unknown.

    Args:
        cases: 用例列表。
        exam: exam 参数。
        profile: profile 参数。
        profile_id: profile 标识。
        subject_kind: subject_kind 参数。
    """
    pid = str(profile_id or "").strip()
    if not pid and exam and isinstance(exam, Mapping):
        plan = exam.get("evaluation_plan")
        pid = str(
            exam.get("profile_id")
            or (
                plan.get("profile_id")
                if isinstance(plan, Mapping)
                else ""
            )
            or ""
        ).strip()
    sk = str(subject_kind or "").strip()
    if not sk and exam and isinstance(exam, Mapping):
        sk = str(exam.get("subject_kind") or "").strip()

    bank, kind, prof = resolve_coverage_context(
        profile=profile,
        profile_id=pid,
        subject_kind=sk,
        cases=cases,
    )
    in_scope, out_of_scope = subject_capability_scope(kind)
    coverage = analyze_capability_coverage(
        bank,
        profile=prof,
        profile_id=pid,
        subject_kind=kind,
    )

    by_cap_bank: Dict[str, int] = defaultdict(int)
    for c in bank:
        cap = _cap_of_case(c)
        if cap in in_scope:
            by_cap_bank[cap] += 1

    selected: Dict[str, int] = defaultdict(int)
    pass_n: Dict[str, int] = defaultdict(int)
    fail_n: Dict[str, int] = defaultdict(int)
    error_n: Dict[str, int] = defaultdict(int)
    skipped_n: Dict[str, int] = defaultdict(int)

    exam_cases = []
    if exam and isinstance(exam.get("cases"), list):
        exam_cases = [x for x in exam["cases"] if isinstance(x, Mapping)]
    for row in exam_cases:
        cap = str(row.get("capability_id") or "").strip()
        if not cap:
            continue
        st = str(row.get("status") or "")
        if st == "skipped":
            skipped_n[cap] += 1
            continue
        selected[cap] += 1
        if st == "pass":
            pass_n[cap] += 1
        elif st == "fail":
            fail_n[cap] += 1
        elif st == "error":
            error_n[cap] += 1

    # Prefer plan quota_trace when attached
    plan = (
        exam.get("evaluation_plan")
        if exam and isinstance(exam.get("evaluation_plan"), Mapping)
        else {}
    )
    quota_trace = []
    if isinstance(plan, Mapping):
        sel = plan.get("selection") if isinstance(plan.get("selection"), Mapping) else {}
        quota_trace = list(sel.get("quota_trace") or [])
    quota_by_cap = {
        str(t.get("capability_id") or ""): t
        for t in quota_trace
        if isinstance(t, Mapping)
    }

    rows: List[Dict[str, Any]] = []
    for cid in sorted(in_scope):
        gap_row = next(
            (g for g in (coverage.get("gaps") or []) if g.get("capability_id") == cid),
            {},
        )
        qt = quota_by_cap.get(cid) or {}
        need = int(gap_row.get("need") or qt.get("quota") or 0)
        have = int(by_cap_bank.get(cid, 0))
        sel_n = int(selected.get(cid, 0) or qt.get("taken") or 0)
        rows.append(
            {
                "capability_id": cid,
                "cases": have,
                "need": need,
                "selected": sel_n,
                "pass": int(pass_n.get(cid, 0)),
                "fail": int(fail_n.get(cid, 0)),
                "error": int(error_n.get(cid, 0)),
                "skipped_holdout": int(skipped_n.get(cid, 0)),
                "gap": max(0, need - have),
                "status": "ok"
                if have >= need and need > 0
                else ("gap" if need > 0 else "empty"),
            }
        )

    unknown_caps = sorted(out_of_scope)
    return {
        "ok": True,
        "schema": "eval.capability_heatmap.v1",
        "subject_kind": kind,
        "profile_id": (prof or {}).get("profile_id")
        or (exam or {}).get("profile_id")
        or pid
        or None,
        "rows": rows,
        "unknown_capabilities": [
            {"capability_id": c, "status": "unknown", "reason": "out_of_scope_v1"}
            for c in unknown_caps
        ],
        "n_gaps": sum(1 for r in rows if r["gap"] > 0),
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            f"coverage heatmap only (subject={kind}); gap≠fail; unknown≠pass; "
            "not an accuracy/sufficiency claim"
        ),
    }


def build_suite_profile_report(
    exam: Mapping[str, Any],
    *,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compose heatmap + §11 disclosure from an exam payload.

    Args:
        exam: exam 参数。
        cases: 用例列表。
    """
    plan = (
        exam.get("evaluation_plan")
        if isinstance(exam.get("evaluation_plan"), Mapping)
        else {}
    )
    heatmap = build_capability_heatmap(
        cases=cases,
        exam=exam,
        profile_id=str(exam.get("profile_id") or plan.get("profile_id") or ""),
        subject_kind=str(exam.get("subject_kind") or plan.get("subject_kind") or ""),
    )
    pack_ref = plan.get("pack_ref") if isinstance(plan.get("pack_ref"), Mapping) else {}
    suite = (
        plan.get("suite_profile")
        if isinstance(plan.get("suite_profile"), Mapping)
        else {}
    )
    plan_counts = plan.get("counts") if isinstance(plan.get("counts"), Mapping) else {}
    disclosure = {
        "pack_id": pack_ref.get("pack_id") or suite.get("pack_id"),
        "pack_version": pack_ref.get("version") or suite.get("pack_version"),
        "profile_id": exam.get("profile_id") or plan.get("profile_id"),
        "subject_kind": heatmap.get("subject_kind")
        or exam.get("subject_kind")
        or plan.get("subject_kind"),
        "plan_id": exam.get("plan_id") or plan.get("plan_id"),
        "manifest_hash": exam.get("manifest_hash") or plan.get("manifest_hash"),
        "execution_fingerprint": exam.get("execution_fingerprint")
        or plan.get("execution_fingerprint"),
        "claim_eligible": False,
        "accuracy_claim": False,
        "live": bool(exam.get("live")),
        "manifest_case_count": exam.get("manifest_case_count"),
        "executed_case_count": exam.get("executed_case_count"),
        "unknown_capabilities": [
            u["capability_id"] for u in heatmap.get("unknown_capabilities") or []
        ],
        "holdout_n": plan_counts.get("holdout"),
        "limits": [
            "dry≠live subject claim"
            if not exam.get("live")
            else "live LLM + lexical oracle only",
            "out_of_scope capabilities reported as unknown",
            "claim_eligible remains false",
        ],
    }

    counts = exam.get("counts") if isinstance(exam.get("counts"), Mapping) else {}
    return {
        "ok": bool(exam.get("ok", True)),
        "schema": "eval.suite_profile_report.v1",
        "subject_kind": heatmap.get("subject_kind"),
        "disclosure": disclosure,
        "heatmap": heatmap,
        "counts": counts,
        "msg": exam.get("msg"),
        "honesty": exam.get("honesty") or heatmap.get("honesty"),
        "claim_eligible": False,
        "accuracy_claim": False,
        "sufficiency_claim": False,
    }
