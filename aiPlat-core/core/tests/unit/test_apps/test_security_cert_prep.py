"""CERT-PREP track: family classify + judge/G2b workflow + L5 rehearsal locks."""
from __future__ import annotations

from core.apps.eval.service.security_cert_prep import (
    build_g2b_s_dual_review_workflow,
    build_judge_calib_evidence_pack,
    rehearse_l5_limited_claim,
    run_per_family_cert_prep,
    security_cert_prep_status,
)
from core.apps.eval.service.security_judge_calib import ASR_UNCALIBRATED


def test_per_family_annotation_fixture_not_l5_candidate():
    run = run_per_family_cert_prep(use_seed_annotation_fixture=True)
    assert run["ok"] is True
    assert run["annotation_only"] is True
    assert run["l5_candidate_families"] == []
    assert run["security_certification"] is False
    assert run["accuracy_claim"] is False


def test_per_family_scored_ready_vs_report_only():
    # Enough T01 samples to meet typical min_n if catalog has one; otherwise report_only.
    by_case = {
        f"c{i}": {"threat_ids": ["T01"], "ok": True} for i in range(30)
    }
    run = run_per_family_cert_prep(by_case=by_case)
    assert run["ok"] is True
    assert run["annotation_only"] is False
    assert run["n_cases"] == 30
    assert "T01" in (
        run["l5_candidate_families"] + run["report_only_families"] + run["untested_families"]
    )
    assert run["l5_declare_allowed_families"] == []
    assert run["claim_eligible"] is False


def test_judge_evidence_uncalibrated_without_pairs():
    pack = build_judge_calib_evidence_pack()
    assert pack["ok"] is True
    assert pack["judge_usable_for_l5_candidate"] is False
    assert pack["asr_calibration_status"] != "calibrated_engineering"
    assert pack["security_certification"] is False


def test_g2b_dual_review_pending_on_failures():
    wf = build_g2b_s_dual_review_workflow(
        security_failure_ids=["f1", "f2"],
        dual_reviews={
            "f1": {
                "reviewer_a": "alice",
                "reviewer_b": "bob",
                "independent_blind": True,
            }
        },
    )
    assert wf["dual_review_completed_ids"] == ["f1"]
    assert "f2" in wf["dual_review_pending_ids"]
    assert wf["all_security_failures_dual_reviewed"] is False
    assert wf["accuracy_claim"] is False


def test_l5_rehearsal_never_certifies_even_with_authorize():
    out = rehearse_l5_limited_claim(
        explicit_authorize=True,
        asr_calibration_status=ASR_UNCALIBRATED,
        judge_usable=False,
        signoffs={
            "method_owner": "m",
            "engineering_owner": "e",
            "security_owner": "s",
        },
    )
    assert out["rehearsal_only"] is True
    assert out["l5_declare_emitted"] is False
    assert out["security_certification"] is False
    assert out["accuracy_claim"] is False
    assert out["claims_gate"]["accuracy_claim"] is False
    assert out["claims_gate"]["security_certification"] is False


def test_cert_prep_status_and_facade():
    st = security_cert_prep_status()
    assert st["slice"] == "CERT-PREP"
    assert st["ok"] is True
    assert st["security_certification"] is False
    assert "score_live_per_family_runs" in st["next_human_gates"]

    from core.api.core_facade import (
        eval_rehearse_l5_limited_claim,
        eval_run_per_family_cert_prep,
        eval_security_cert_prep_status,
    )

    assert eval_security_cert_prep_status()["ok"] is True
    assert eval_run_per_family_cert_prep(use_seed_annotation_fixture=True)["annotation_only"]
    assert eval_rehearse_l5_limited_claim()["security_certification"] is False
