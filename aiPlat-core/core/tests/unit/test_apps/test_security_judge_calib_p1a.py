"""SEC-P1a: judge calibration protocol + judge_version manifest."""
from __future__ import annotations

import pytest

from core.apps.eval.service.security_judge_calib import (
    ASR_CALIBRATED,
    ASR_UNCALIBRATED,
    ASR_VERSION_DRIFT,
    SecurityJudgeCalibError,
    annotate_family_asr_calibration,
    assert_judge_model_isolation,
    build_judge_version_manifest,
    check_judge_version_drift,
    evaluate_security_judge_calibration,
    load_judge_calib_defaults,
    security_sec_p1a_status,
)


def test_defaults_load_honesty_locks():
    defs = load_judge_calib_defaults()
    assert defs["schema"].startswith("eval.security_judge_calib_defaults")
    assert defs["accuracy_claim"] is False
    assert defs["security_certification"] is False
    assert float(defs["defaults"]["agreement_threshold"]) == 0.8


def test_self_judge_forbidden():
    iso = assert_judge_model_isolation(
        judge_model="qwen2.5:32b", subject_model="qwen2.5:32b"
    )
    assert iso["isolated"] is False
    assert iso["violation"] == "self_judge_forbidden"
    with pytest.raises(SecurityJudgeCalibError, match="self_judge"):
        build_judge_version_manifest(
            judge_id="j1",
            judge_version="1.0",
            judge_model="same-model",
            subject_model="same-model",
        )


def test_manifest_and_no_drift():
    m = build_judge_version_manifest(
        judge_id="security.policy_judge",
        judge_version="1.2.0",
        judge_model="judge-llm",
        subject_model="subject-llm",
        prompt_hash="abc",
    )
    assert m["schema"] == "eval.security_judge_version_manifest.v1"
    assert m["frozen"] is True
    assert m["claim_eligible"] is False
    d = check_judge_version_drift(run_manifest=m, frozen_manifest=m)
    assert d["drifted"] is False
    assert d["claim_candidate_invalid"] is False


def test_version_drift_invalidates_claim_candidate():
    frozen = build_judge_version_manifest(
        judge_id="j",
        judge_version="1.0.0",
        judge_model="judge-a",
        subject_model="subj",
        prompt_hash="h1",
    )
    run = dict(frozen)
    run["judge_version"] = "1.0.1"
    d = check_judge_version_drift(run_manifest=run, frozen_manifest=frozen)
    assert d["drifted"] is True
    assert d["claim_candidate_invalid"] is True
    assert any(x["field"] == "judge_version" for x in d["diffs"])


def _perfect_pairs(n: int = 10):
    # gold==judge for all; mix of True/False so FP/FN rates are 0
    out = []
    for i in range(n):
        label = i % 2 == 0
        out.append({"case_id": f"c{i}", "gold": label, "judge": label})
    return out


def test_calibration_meets_engineering_bar():
    manifest = build_judge_version_manifest(
        judge_id="j",
        judge_version="1.0.0",
        judge_model="judge-a",
        subject_model="subj",
    )
    report = evaluate_security_judge_calibration(
        pairs=_perfect_pairs(10),
        manifest=manifest,
        frozen_manifest=manifest,
        failure_case_ids=[],
    )
    assert report["meets_engineering_bar"] is True
    assert report["asr_status"] == ASR_CALIBRATED
    assert report["metrics"]["agreement"] == 1.0
    assert report["metrics"]["false_positive_rate"] == 0.0
    assert report["l5_eligible"] is False
    assert report["accuracy_claim"] is False


def test_calibration_uncalibrated_on_disagreement():
    pairs = [{"case_id": f"c{i}", "gold": True, "judge": False} for i in range(10)]
    report = evaluate_security_judge_calibration(pairs=pairs, failure_case_ids=[])
    assert report["meets_engineering_bar"] is False
    assert report["asr_status"] == ASR_UNCALIBRATED
    assert "agreement_below_threshold" in " ".join(report["reasons"])


def test_dual_human_required_when_failures():
    manifest = build_judge_version_manifest(
        judge_id="j",
        judge_version="1.0.0",
        judge_model="judge-a",
        subject_model="subj",
    )
    report = evaluate_security_judge_calibration(
        pairs=_perfect_pairs(10),
        manifest=manifest,
        frozen_manifest=manifest,
        failure_case_ids=["fail-1"],
    )
    assert report["meets_engineering_bar"] is False
    assert "dual_human_review_required_on_failures" in report["reasons"]

    manifest2 = dict(manifest)
    manifest2["dual_human_completed"] = True
    report2 = evaluate_security_judge_calibration(
        pairs=_perfect_pairs(10),
        manifest=manifest2,
        frozen_manifest=manifest,
        failure_case_ids=["fail-1"],
    )
    # frozen vs run prompt/fields same except dual flag — still ok
    assert report2["meets_engineering_bar"] is True


def test_drift_in_calibration_report():
    frozen = build_judge_version_manifest(
        judge_id="j",
        judge_version="1.0.0",
        judge_model="judge-a",
        subject_model="subj",
    )
    run = dict(frozen)
    run["judge_model"] = "judge-b"
    report = evaluate_security_judge_calibration(
        pairs=_perfect_pairs(10),
        manifest=run,
        frozen_manifest=frozen,
        failure_case_ids=[],
    )
    assert report["meets_engineering_bar"] is False
    assert report["asr_status"] == ASR_VERSION_DRIFT


def test_annotate_family_report_stamps_uncalibrated():
    family = {
        "families": {
            "T01": {"n": 5, "rate": 0.2, "claim_eligible": False},
        }
    }
    calib = {
        "meets_engineering_bar": False,
        "asr_status": ASR_UNCALIBRATED,
    }
    out = annotate_family_asr_calibration(family, calib=calib)
    assert out["families"]["T01"]["asr_calibration_status"] == ASR_UNCALIBRATED
    assert out["families"]["T01"]["judge_usable"] is False
    assert out["accuracy_claim"] is False


def test_p1a_status_card():
    st = security_sec_p1a_status()
    assert st["schema"] == "eval.security_sec_p1a_status.v1"
    assert st["slice"] == "SEC-P1a"
    assert st["judge_version_manifest"]["judge_id"]
    assert st["accuracy_claim"] is False
    assert st["security_certification"] is False
    assert st["protocol"]["self_judge_forbidden"] is True
