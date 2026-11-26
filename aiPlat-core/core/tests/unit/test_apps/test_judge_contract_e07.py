"""评测 Extended E07 — Judge 校准字段契约。"""
from __future__ import annotations

from core.apps.eval.service.judge_contract import normalize_judge_report


def test_normalize_forces_explicit_calibration_ref_none():
    out = normalize_judge_report({"judge_id": "j1", "score": 0.9})
    assert out["judge_id"] == "j1"
    assert "calibration_ref" in out
    assert out["calibration_ref"] is None
    assert out["accuracy_gate_eligible"] is False
    assert out["calibrated"] is False


def test_normalize_with_report_id_as_calibration_ref():
    out = normalize_judge_report(
        {"judge_id": "judge.v1", "report_id": "rep-abc", "accuracy_claim": False}
    )
    assert out["calibration_ref"] == "rep-abc"
    assert out["calibrated"] is True
    assert out["accuracy_gate_eligible"] is True
    assert out["accuracy_claim"] is False


def test_empty_calibration_ref_blocks_accuracy_gate():
    out = normalize_judge_report(
        {"judge_id": "j1", "calibration_ref": "", "calibrated": True}
    )
    assert out["calibration_ref"] is None
    assert out["accuracy_gate_eligible"] is False


def test_default_judge_id_fill():
    out = normalize_judge_report({}, default_judge_id="fallback.judge")
    assert out["judge_id"] == "fallback.judge"
    assert out["calibration_ref"] is None
