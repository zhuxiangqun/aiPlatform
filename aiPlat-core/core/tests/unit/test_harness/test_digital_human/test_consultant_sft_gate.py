"""consultant_sft_gate：holdout 结构门与诚实锁。"""
from __future__ import annotations

from core.harness.digital_human.consultant_sft_gate import (
    DH_SFT_HOLDOUT_VERSION,
    evaluate_sft_promote_gate,
)


def test_gate_pass_with_job(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_TRAJECTORY_DIR", str(tmp_path / "traj"))
    monkeypatch.delenv("AIPLAT_DH_SFT_PROMOTE_SKIP_GATE", raising=False)
    r = evaluate_sft_promote_gate(
        payload={
            "job_id": "j1",
            "sample_count": 12,
            "good_rate": 0.9,
            "rated_count": 12,
        },
    )
    assert r["ok"] is True
    assert r["passed"] is True
    assert r["production_model_changed"] is False
    assert r["feeds_production_routing"] is False
    assert r["e5_claimed"] is False
    assert r["dataset_version"] == DH_SFT_HOLDOUT_VERSION
    assert r["n_cases"] >= 1
    assert r["goal_id"] == "consultant.sft_quality.v1"


def test_gate_fail_without_job(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_TRAJECTORY_DIR", str(tmp_path / "traj"))
    monkeypatch.delenv("AIPLAT_DH_SFT_PROMOTE_SKIP_GATE", raising=False)
    r = evaluate_sft_promote_gate(payload={})
    assert r["passed"] is False
    assert r["feeds_production_routing"] is False
