"""SEC-P2b: L5 scope-bound claim template (per threat family).

Builds the Appendix-B style disclosure sentence and structured family rows.
Default: accuracy_claim=false, security_certification=false, claim_eligible=false.

Rules:
- Only engineering_ready families may enter declare_candidate set
- severity-blocked / uncalibrated / below_min_n / untested / deferred stay excluded
- Forbidden marketing sentences rejected
- explicit_authorize alone never flips security_certification
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.security_family_report import build_security_family_report
from core.apps.eval.service.security_s1_disclosure import build_untested_oos_disclosure

TEMPLATE_SCHEMA = "eval.security_l5_claim_template.v1"
STATUS_SCHEMA = "eval.security_sec_p2b_status.v1"

FORBIDDEN_PATTERNS = (
    r"已通过\s*Agent\s*安全评测",
    r"已通过安全评测",
    r"可上生产",
    r"security\s*certification\s*passed",
    r"L1\s*全过.*生产",
    r"microVM\s*已\s*covered",
    r"admit\s*=\s*covered",
)


class SecurityL5ClaimTemplateError(ValueError):
    """Fail-closed L5 claim template error."""


def _fmt_rate(v: Any) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_ci(ci: Any) -> str:
    if not isinstance(ci, (list, tuple)) or len(ci) < 2:
        return ""
    try:
        return f"CI95=[{float(ci[0]):.2f},{float(ci[1]):.2f}]"
    except (TypeError, ValueError):
        return ""


def detect_forbidden_claim_phrases(text: str) -> List[str]:
    hits: List[str] = []
    s = str(text or "")
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, s, flags=re.IGNORECASE):
            hits.append(pat)
    return hits


def select_declare_candidate_families(
    *,
    family_report: Mapping[str, Any],
    severity_blocked: Optional[Sequence[str]] = None,
    judge_usable: bool = True,
    asr_calibration_status: str = "",
) -> Dict[str, Any]:
    """Pick families eligible for L5 *template* candidate set (not auto-declare)."""
    fams = family_report.get("families") if isinstance(family_report.get("families"), Mapping) else {}
    blocked = {str(x) for x in (severity_blocked or [])}
    calib = str(asr_calibration_status or "").strip()
    uncalibrated = calib in {"judge_uncalibrated", "self_judge_forbidden", "judge_version_drift"}
    if not judge_usable or uncalibrated:
        return {
            "declare_candidate_families": [],
            "excluded": {
                "judge_not_usable": sorted(fams.keys()) if fams else ["*"],
            },
            "reasons": ["judge_not_calibrated_or_unusable"],
        }

    candidates: List[str] = []
    excluded: Dict[str, List[str]] = {
        "not_engineering_ready": [],
        "severity_blocked": [],
        "untested": [],
        "report_only": [],
    }
    for fid, row in fams.items():
        if not isinstance(row, Mapping):
            continue
        sid = str(fid)
        st = str(row.get("status") or "")
        if sid in blocked:
            excluded["severity_blocked"].append(sid)
            continue
        if st == "engineering_ready":
            candidates.append(sid)
        elif st == "untested":
            excluded["untested"].append(sid)
        elif st == "report_only":
            excluded["report_only"].append(sid)
        else:
            excluded["not_engineering_ready"].append(sid)

    return {
        "declare_candidate_families": sorted(candidates),
        "excluded": {k: sorted(v) for k, v in excluded.items() if v},
        "reasons": [],
    }


def render_l5_claim_sentence(
    *,
    subject: Mapping[str, Any],
    pack_id: str,
    pack_version: str,
    runtime_tier: str,
    judge_id: str,
    judge_version: str,
    family_rows: Sequence[Mapping[str, Any]],
    excluded_ids: Sequence[str],
) -> str:
    """Appendix-B style allowed sentence (engineering draft)."""
    s_label = str(
        subject.get("label")
        or subject.get("subject_id")
        or subject.get("object_id")
        or "S=?"
    )
    parts: List[str] = []
    for row in family_rows:
        tid = str(row.get("threat_id") or "")
        n = row.get("n")
        rate = _fmt_rate(row.get("rate"))
        metric = str(row.get("metric") or "rate")
        ci = _fmt_ci(row.get("wilson_ci95"))
        chunk = f"{tid} n={n} {metric}={rate}"
        if ci:
            chunk += f" {ci}"
        parts.append(chunk)
    fam_txt = "；".join(parts) if parts else "（无达标族）"
    excl = "、".join(str(x) for x in excluded_ids) if excluded_ids else "无"
    return (
        f"S={s_label}, R={runtime_tier}, J={judge_id}@{judge_version}, "
        f"P={pack_id}@{pack_version}："
        f"{fam_txt}；未包含/未达标 {{{excl}}}；非 certification。"
    )


def build_security_l5_claim_template(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    subject: Optional[Mapping[str, Any]] = None,
    pack_id: str = "agent.safety.l1",
    pack_version: str = "0.0.0",
    runtime_tier: str = "workspace_execute",
    judge_id: str = "security.policy_judge",
    judge_version: str = "1.0.0",
    severity_blocked: Optional[Sequence[str]] = None,
    judge_usable: bool = True,
    asr_calibration_status: str = "judge_uncalibrated",
    explicit_authorize: bool = False,
    signoffs: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build per-family L5 claim template. Never auto-certifies."""
    subj = dict(subject or {})
    report = build_security_family_report(
        by_case=by_case or {},
        subject=subj,
        pack_id=pack_id,
        eval_layer="L1",
    )
    disclosure = build_untested_oos_disclosure(by_case=by_case or {})
    selection = select_declare_candidate_families(
        family_report=report,
        severity_blocked=severity_blocked,
        judge_usable=judge_usable,
        asr_calibration_status=asr_calibration_status,
    )
    candidates = list(selection.get("declare_candidate_families") or [])
    fams = report.get("families") if isinstance(report.get("families"), Mapping) else {}
    family_rows: List[Dict[str, Any]] = []
    for tid in candidates:
        row = fams.get(tid) if isinstance(fams.get(tid), Mapping) else {}
        family_rows.append(
            {
                "threat_id": tid,
                "n": row.get("n"),
                "rate": row.get("rate"),
                "wilson_ci95": row.get("wilson_ci95"),
                "metric": row.get("metric") or "ASR",
                "status": row.get("status"),
                "claim_eligible": False,
            }
        )

    excluded_ids = sorted(
        set(disclosure.get("untested_threat_families") or [])
        | set(disclosure.get("below_min_n_families") or [])
        | set(disclosure.get("deferred_threat_families") or [])
        | set(disclosure.get("oos_ids") or [])
        | {
            x
            for xs in (selection.get("excluded") or {}).values()
            for x in (xs or [])
        }
    )
    # Keep candidates out of excluded display list
    excluded_ids = [x for x in excluded_ids if x not in set(candidates)]

    sentence = render_l5_claim_sentence(
        subject=subj,
        pack_id=pack_id,
        pack_version=pack_version,
        runtime_tier=runtime_tier,
        judge_id=judge_id,
        judge_version=judge_version,
        family_rows=family_rows,
        excluded_ids=excluded_ids,
    )
    forbidden = detect_forbidden_claim_phrases(sentence)
    if forbidden:
        raise SecurityL5ClaimTemplateError(f"forbidden_phrase:{forbidden}")

    sig = dict(signoffs or {})
    signoff_complete = bool(
        sig.get("method_owner")
        and sig.get("engineering_owner")
        and sig.get("security_owner")
    )

    # Even with authorize, certification stays false in this slice —
    # template + gate disclosure only (SEC-P2b ≠ certification issuance).
    authorize_requested = bool(explicit_authorize)
    blockers: List[str] = []
    if not candidates:
        blockers.append("no_declare_candidate_families")
    if (not judge_usable) or asr_calibration_status != "calibrated_engineering":
        blockers.append("judge_not_calibrated_engineering")
    if not signoff_complete:
        blockers.append("triple_signoff_incomplete")
    if authorize_requested and blockers:
        blockers.append("authorize_blocked")

    return {
        "schema": TEMPLATE_SCHEMA,
        "ok": True,
        "subject": subj,
        "pack_id": pack_id,
        "pack_version": pack_version,
        "runtime_tier": runtime_tier,
        "judge_id": judge_id,
        "judge_version": judge_version,
        "declare_candidate_families": candidates,
        "family_rows": family_rows,
        "excluded_threat_families": excluded_ids,
        "untested_threat_families": list(disclosure.get("untested_threat_families") or []),
        "below_min_n_families": list(disclosure.get("below_min_n_families") or []),
        "deferred_threat_families": list(disclosure.get("deferred_threat_families") or []),
        "oos_ids": list(disclosure.get("oos_ids") or []),
        "selection": selection,
        "claim_sentence": sentence,
        "forbidden_phrase_hits": [],
        "signoffs": sig,
        "signoff_complete": signoff_complete,
        "explicit_authorize": authorize_requested,
        "blockers": blockers,
        "l5_declare_emitted": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Per-family L5 claim *template* only. "
            "declare_candidate ≠ emitted declaration ≠ certification. "
            "accuracy_claim/security_certification stay false in SEC-P2b."
        ),
    }


def validate_claim_sentence_against_policy(sentence: str) -> Dict[str, Any]:
    """Reject forbidden marketing / false-green sentences."""
    hits = detect_forbidden_claim_phrases(sentence)
    return {
        "schema": "eval.security_l5_claim_sentence_validate.v1",
        "ok": not hits,
        "forbidden_phrase_hits": hits,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": "Forbidden phrases must never appear in L5 disclosures",
    }


def security_sec_p2b_status(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    subject: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Facade-friendly SEC-P2b status: empty/sample template + locks."""
    # Default sample: no scored runs → empty candidates (honest)
    tmpl = build_security_l5_claim_template(
        by_case=by_case or {},
        subject=subject or {"label": "demo-subject", "object_id": "demo"},
        asr_calibration_status="judge_uncalibrated",
        judge_usable=False,
    )
    bad = validate_claim_sentence_against_policy("已通过 Agent 安全评测，可上生产。")
    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "slice": "SEC-P2b",
        "template": tmpl,
        "forbidden_example_rejected": bad,
        "allowed_sentence_shape": (
            "S=…, R=…, J=…@…, P=…@…：Txx n=… rate=…；未包含/未达标 {…}；非 certification。"
        ),
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "SEC-P2b L5 per-family claim template. "
            "No auto certification; forbidden phrases rejected."
        ),
    }
