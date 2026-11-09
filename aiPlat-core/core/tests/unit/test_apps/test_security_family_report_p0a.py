"""SEC-P0a: T05-text vs T05-exec boundary + per-family report schema."""
from __future__ import annotations

import pytest

from core.apps.eval.service.security_family_report import (
    SecurityFamilyReportError,
    build_security_family_report,
    l1_forbidden_threats,
    load_l1_safety_cases_from_seed,
    load_threat_family_catalog,
    security_l1_p0a_status,
    validate_case_threat_ids,
    validate_l1_safety_cases,
)


def test_catalog_loads_and_forbids_exec_on_l1():
    cat = load_threat_family_catalog()
    assert cat["schema"].startswith("eval.security_threat_family_catalog")
    assert cat["accuracy_claim"] is False
    forbidden = set(l1_forbidden_threats(cat))
    assert "T05-exec" in forbidden
    assert "T06" in forbidden
    assert "T05-text-refusal" in set(cat["l1_allowed"])


def test_l1_safety_cases_annotated():
    cases = load_l1_safety_cases_from_seed()
    assert len(cases) >= 8
    for c in cases:
        assert c.get("eval_layer") == "L1"
        assert c.get("threat_ids")
        assert c.get("claim_boundary", {}).get("prevents_destructive_execution") is False
    # Destructive text cases must be T05-text-refusal, never T05-exec
    by_id = {c["case_id"]: c for c in cases}
    assert by_id["agent.safety.001"]["threat_ids"] == ["T05-text-refusal"]
    assert by_id["agent.safety.006"]["threat_ids"] == ["T05-text-refusal"]
    assert "T05-exec" not in by_id["agent.safety.001"]["threat_ids"]


def test_validate_rejects_t05_exec_on_l1():
    errs = validate_case_threat_ids(
        {
            "case_id": "bad",
            "threat_ids": ["T05-exec"],
            "eval_layer": "L1",
        }
    )
    assert "l1_forbidden_threat:T05-exec" in errs or "t05_exec_requires_l3" in errs


def test_validate_l1_bank_passes():
    cases = load_l1_safety_cases_from_seed()
    out = validate_l1_safety_cases(cases)
    assert out["ok"] is True, out


def test_family_report_no_macro_claim():
    report = build_security_family_report(
        by_case={
            "c1": {"threat_ids": ["T01"], "ok": False},
            "c2": {"threat_ids": ["T01"], "ok": True},
            "c3": {"threat_ids": ["T03"], "ok": True},
        }
    )
    assert report["schema"] == "eval.security_family_report.v1"
    assert report["macro_asr_not_for_claim"] is True
    assert report["accuracy_claim"] is False
    assert report["security_certification"] is False
    assert report["families"]["T01"]["n"] == 2
    assert report["families"]["T01"]["rate"] == 0.5
    # n=2 << min_n_l5 → report_only
    assert report["families"]["T01"]["status"] == "report_only"
    assert report["families"]["T01"]["wilson_ci95"] is not None
    assert "T01" in report["below_min_n_families"]
    assert report["l5_declare_allowed_families"] == []
    assert "T05-exec" in report["untested_threat_families"]
    assert "OOS-01" in report["out_of_scope"]


def test_family_gate_engineering_ready_when_min_n_met():
    from core.apps.eval.service.security_family_report import security_sec_p0c_status

    # T09 min_n_l5=10
    by_case = {
        f"c{i}": {"threat_ids": ["T09"], "ok": True} for i in range(10)
    }
    report = build_security_family_report(by_case=by_case)
    assert report["families"]["T09"]["status"] == "engineering_ready"
    assert report["families"]["T09"]["meets_min_n"] is True
    assert "T09" in report["engineering_ready_families"]
    assert report["claim_eligible"] is False
    assert report["l5_declare_allowed_families"] == []
    st = security_sec_p0c_status(by_case=by_case)
    assert st["slice"] == "SEC-P0c"
    assert st["accuracy_claim"] is False
    from core.api.core_facade import eval_security_sec_p0c_status

    assert eval_security_sec_p0c_status(by_case)["ok"] is True


def test_sec_p0a_status_and_facade():
    st = security_l1_p0a_status()
    assert st["ok"] is True
    assert st["slice"] == "SEC-P0a"
    assert st["l3_exec_deferred"]["n_cases"] == 0
    assert st["accuracy_claim"] is False
    from core.api.core_facade import eval_security_sec_p0a_status

    assert eval_security_sec_p0a_status()["ok"] is True
