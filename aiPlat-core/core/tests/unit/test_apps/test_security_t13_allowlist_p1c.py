"""SEC-P1c: T13 allowlist pack + process_split boundary."""
from __future__ import annotations

from core.apps.eval.service.security_t13_allowlist import (
    COV_CLAIM_CANDIDATE,
    COV_FIXTURE,
    assert_t13_process_split_boundary,
    evaluate_t13_coverage,
    load_t13_allowlist_probes,
    run_t13_allowlist_probes,
    security_sec_p1c_status,
)


def test_pack_loads_min_ten_t13_with_boundary_assert():
    cat = load_t13_allowlist_probes()
    assert cat["schema"].startswith("eval.security_t13_allowlist_probes")
    assert cat["process_split_required"] is False
    assert cat["accuracy_claim"] is False
    t13_only = [c for c in cat["cases"] if c.get("threat_ids") == ["T13"]]
    assert len(t13_only) >= 10
    assert any(c.get("assert_process_split_not_required") for c in t13_only)
    assert any(c.get("kind") == "negative_control" for c in t13_only)
    escape = [c for c in cat["cases"] if "T13-escape" in c.get("threat_ids", [])]
    assert escape
    assert all(c.get("require_process_split_authorized") for c in escape)


def test_fixture_run_all_pass_without_process_split():
    run = run_t13_allowlist_probes(coverage_mode=COV_FIXTURE)
    assert run["t13_all_pass"] is True
    assert run["process_split_required"] is False
    assert run["process_split_authorized"] is False
    assert run["accuracy_claim"] is False
    assert run["n_t13"] >= 10
    # Escape deferred
    esc = [
        r
        for r in run["results"]
        if "T13-escape" in (r.get("threat_ids") or [])
    ]
    assert esc
    assert all(r.get("decision") == "deferred" for r in esc)


def test_process_split_input_does_not_authorize():
    run = run_t13_allowlist_probes(process_split_authorized=True)
    assert run["process_split_authorized"] is False
    boundary = assert_t13_process_split_boundary(run=run)
    assert boundary["ok"] is True
    assert boundary["process_split_authorized"] is False


def test_deny_cases_actually_deny():
    run = run_t13_allowlist_probes()
    by_id = {r["case_id"]: r for r in run["results"]}
    assert by_id["t13.unsigned_skill_denied"]["decision"] == "deny"
    assert by_id["t13.tampered_signature_denied"]["decision"] == "deny"
    assert by_id["t13.missing_load_trace_denied"]["decision"] == "deny"
    assert by_id["t13.allowlisted_signed_skill_allowed"]["decision"] == "allow"
    assert by_id["t13.allowlisted_signed_skill_allowed"]["load_trace"] is not None


def test_coverage_claim_candidate_still_claim_closed():
    run = run_t13_allowlist_probes()
    cov = evaluate_t13_coverage(
        run, human_review=True, human_reviewer="qa"
    )
    assert cov["coverage"] == COV_CLAIM_CANDIDATE
    assert cov["claim_eligible"] is False
    assert cov["accuracy_claim"] is False
    assert cov["l5_declare_allowed"] is False
    assert cov["process_split_authorized"] is False


def test_p1c_status_card():
    st = security_sec_p1c_status(human_review=True, human_reviewer="qa")
    assert st["schema"] == "eval.security_sec_p1c_status.v1"
    assert st["slice"] == "SEC-P1c"
    assert st["ok"] is True
    assert st["boundary"]["ok"] is True
    assert st["process_split_authorized"] is False
    assert st["security_certification"] is False
