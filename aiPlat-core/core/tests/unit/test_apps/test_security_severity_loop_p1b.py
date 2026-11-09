"""SEC-P1b: severity / remediation / retest / claim_revocation."""
from __future__ import annotations

import pytest

from core.apps.eval.service.security_severity_loop import (
    SecuritySeverityLoopError,
    build_security_finding,
    evaluate_claim_revocation,
    evaluate_severity_l5_gate,
    load_severity_loop_defaults,
    security_sec_p1b_status,
    transition_finding,
)


def test_defaults_honesty_locks():
    defs = load_severity_loop_defaults()
    assert defs["schema"].startswith("eval.security_severity_loop_defaults")
    assert defs["accuracy_claim"] is False
    assert defs["security_certification"] is False
    assert "critical" in defs["defaults"]["l5_block_severities"]


def test_build_finding_requires_owner_and_enums():
    f = build_security_finding(
        case_id="c1",
        threat_id="T01",
        severity="critical",
        impact="data",
        remediation_owner="sec-owner",
        retest_case_id="c1-retest",
    )
    assert f["schema"] == "eval.security_severity_finding.v1"
    assert f["status"] == "open"
    assert f["claim_eligible"] is False
    with pytest.raises(SecuritySeverityLoopError, match="remediation_owner"):
        build_security_finding(
            case_id="c1",
            threat_id="T01",
            severity="low",
            impact="tool",
            remediation_owner="",
        )
    with pytest.raises(SecuritySeverityLoopError, match="invalid_severity"):
        build_security_finding(
            case_id="c1",
            threat_id="T01",
            severity="ultra",
            impact="tool",
            remediation_owner="x",
        )


def test_cannot_close_without_retest_evidence():
    f = build_security_finding(
        case_id="c1",
        threat_id="T05-exec",
        severity="high",
        impact="tool",
        remediation_owner="eng",
        retest_case_id="c1-r",
    )
    with pytest.raises(SecuritySeverityLoopError, match="retest_passed"):
        transition_finding(f, status="retested_pass")
    with pytest.raises(SecuritySeverityLoopError, match="retest_evidence"):
        transition_finding(f, status="retested_pass", retest_passed=True)
    closed = transition_finding(
        f,
        status="retested_pass",
        retest_passed=True,
        retest_evidence="pytest:test_c1_r_pass",
    )
    assert closed["status"] == "retested_pass"
    assert closed["accuracy_claim"] is False


def test_accepted_risk_requires_signoff():
    f = build_security_finding(
        case_id="c2",
        threat_id="T03",
        severity="critical",
        impact="tenant",
        remediation_owner="sec",
    )
    with pytest.raises(SecuritySeverityLoopError, match="signoff"):
        transition_finding(f, status="accepted_risk")
    ok = transition_finding(
        f, status="accepted_risk", accepted_risk_signoff="qa-lead@2026-11-09"
    )
    assert ok["status"] == "accepted_risk"
    assert ok["accepted_risk_signoff"]


def test_open_critical_blocks_l5_family():
    open_f = build_security_finding(
        case_id="c1",
        threat_id="T01",
        severity="critical",
        impact="data",
        remediation_owner="sec",
    )
    low = build_security_finding(
        case_id="c2",
        threat_id="T02",
        severity="low",
        impact="availability",
        remediation_owner="sec",
    )
    gate = evaluate_severity_l5_gate(
        [open_f, low], declare_families=["T01", "T02"]
    )
    assert "T01" in gate["declare_families_blocked"]
    assert "T02" in gate["declare_families_clear"]
    assert gate["l5_declare_allowed_families"] == []
    assert gate["accuracy_claim"] is False

    closed = transition_finding(
        open_f,
        status="retested_pass",
        retest_case_id="c1-r",
        retest_passed=True,
        retest_evidence="ok",
    )
    gate2 = evaluate_severity_l5_gate(
        [closed, low], declare_families=["T01", "T02"]
    )
    assert gate2["declare_families_blocked"] == []
    assert set(gate2["declare_families_clear"]) == {"T01", "T02"}


def test_claim_revocation_on_critical_regression():
    reg = build_security_finding(
        case_id="reg1",
        threat_id="T01",
        severity="critical",
        impact="host",
        remediation_owner="sec",
    )
    rev = evaluate_claim_revocation(
        declared_families=["T01", "T03"],
        new_findings=[reg],
    )
    assert rev["revocation_required"] is True
    assert "T01" in rev["revoked_threat_families"]
    assert "T03" not in rev["revoked_threat_families"]
    assert rev["accuracy_claim"] is False

    none = evaluate_claim_revocation(
        declared_families=["T01"],
        new_findings=[
            build_security_finding(
                case_id="x",
                threat_id="T01",
                severity="medium",
                impact="data",
                remediation_owner="sec",
            )
        ],
    )
    assert none["revocation_required"] is False


def test_p1b_status_card():
    f = build_security_finding(
        case_id="c1",
        threat_id="T12",
        severity="high",
        impact="host",
        remediation_owner="runtime",
    )
    st = security_sec_p1b_status(findings=[f], declared_families=["T12"])
    assert st["schema"] == "eval.security_sec_p1b_status.v1"
    assert st["slice"] == "SEC-P1b"
    assert st["security_certification"] is False
    assert "T12" in st["l5_gate"]["blocked_threat_families"]
    assert st["protocol"]["require_retest_to_close"] is True
