"""SEC-P2b: L5 per-family claim template (claim-closed)."""
from __future__ import annotations

from core.apps.eval.service.security_l5_claim_template import (
    build_security_l5_claim_template,
    detect_forbidden_claim_phrases,
    security_sec_p2b_status,
    select_declare_candidate_families,
    validate_claim_sentence_against_policy,
)
from core.apps.eval.service.security_family_report import build_security_family_report


def _enough_cases(tid: str, n: int, ok_rate: float = 0.9):
    """Build by_case with n samples for one family."""
    out = {}
    ok_n = int(n * ok_rate)
    for i in range(n):
        out[f"{tid}-{i}"] = {"threat_ids": [tid], "ok": i < ok_n}
    return out


def test_forbidden_phrases_rejected():
    hits = detect_forbidden_claim_phrases("已通过 Agent 安全评测，可上生产。")
    assert hits
    v = validate_claim_sentence_against_policy("已通过安全评测")
    assert v["ok"] is False
    assert v["accuracy_claim"] is False


def test_uncalibrated_judge_yields_no_candidates():
    by_case = _enough_cases("T01", 25)
    # Force engineering_ready via report then selection with bad judge
    report = build_security_family_report(by_case=by_case)
    assert report["families"]["T01"]["status"] == "engineering_ready"
    sel = select_declare_candidate_families(
        family_report=report,
        judge_usable=False,
        asr_calibration_status="judge_uncalibrated",
    )
    assert sel["declare_candidate_families"] == []


def test_template_with_calibrated_ready_family():
    by_case = _enough_cases("T01", 25)
    tmpl = build_security_l5_claim_template(
        by_case=by_case,
        subject={"label": "agent-x", "object_id": "agent-x"},
        pack_id="agent.safety.l1",
        pack_version="1.2.0",
        runtime_tier="workspace_execute",
        judge_id="policy_judge",
        judge_version="1.2",
        judge_usable=True,
        asr_calibration_status="calibrated_engineering",
        severity_blocked=[],
        signoffs={
            "method_owner": "a",
            "engineering_owner": "b",
            "security_owner": "c",
        },
        explicit_authorize=True,
    )
    assert "T01" in tmpl["declare_candidate_families"]
    assert tmpl["claim_sentence"].startswith("S=agent-x")
    assert "非 certification" in tmpl["claim_sentence"]
    assert tmpl["accuracy_claim"] is False
    assert tmpl["security_certification"] is False
    assert tmpl["l5_declare_emitted"] is False
    assert tmpl["signoff_complete"] is True
    # authorize still does not emit certification in P2b
    assert "authorize_blocked" not in tmpl["blockers"] or tmpl["security_certification"] is False


def test_severity_blocked_excludes_family():
    by_case = _enough_cases("T01", 25)
    tmpl = build_security_l5_claim_template(
        by_case=by_case,
        subject={"label": "s"},
        judge_usable=True,
        asr_calibration_status="calibrated_engineering",
        severity_blocked=["T01"],
    )
    assert "T01" not in tmpl["declare_candidate_families"]
    assert "T01" in tmpl["selection"]["excluded"]["severity_blocked"]


def test_p2b_status_card_locks():
    st = security_sec_p2b_status()
    assert st["schema"] == "eval.security_sec_p2b_status.v1"
    assert st["slice"] == "SEC-P2b"
    assert st["accuracy_claim"] is False
    assert st["security_certification"] is False
    assert st["forbidden_example_rejected"]["ok"] is False
