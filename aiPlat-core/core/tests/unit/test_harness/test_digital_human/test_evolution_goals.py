"""evolution_goals：五域机读目标 + 诚实锁。"""
from __future__ import annotations

import json

from core.harness.digital_human.evolution_goals import (
    GOAL_CONSULTANT_SFT,
    GOAL_IDS,
    get_evolution_goal,
    goal_progress_for_kind,
    list_evolution_goals,
    measure_all_evolution_goals,
    measure_curated_feedback_rate,
    measure_evolution_goal,
)
from core.harness.digital_human.consultant_sft_gate import evaluate_sft_promote_gate


def test_list_five_goals(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    rows = list_evolution_goals()
    assert len(rows) == 5
    assert {r["goal_id"] for r in rows} == set(GOAL_IDS)
    for r in rows:
        assert r.get("auto_apply") is False
        assert "non_goals" in r


def test_measure_all_honesty(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_TRAJECTORY_DIR", str(tmp_path / "traj"))
    snap = measure_all_evolution_goals()
    assert snap["ok"] is True
    assert snap["e5_claimed"] is False
    assert snap["production_model_changed"] is False
    assert snap["total"] == 5
    for g in snap["goals"]:
        assert g.get("e5_claimed") is False
        assert g.get("feeds_production_routing") is False


def test_curated_good_rate(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    traj = tmp_path / "traj"
    traj.mkdir()
    monkeypatch.setenv("AIPLAT_TRAJECTORY_DIR", str(traj))
    (traj / "s1.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "q1"}),
                json.dumps({"role": "assistant", "content": "a1", "quality": "good"}),
                json.dumps({"role": "user", "content": "q2"}),
                json.dumps({"role": "assistant", "content": "a2", "quality": "bad"}),
                json.dumps({"role": "user", "content": "q3"}),
                json.dumps({"role": "assistant", "content": "a3", "quality": "good"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    r = measure_curated_feedback_rate()
    assert r["baseline_missing"] is False
    assert r["good"] == 2
    assert r["bad"] == 1
    assert abs(r["good_rate"] - 2 / 3) < 1e-9
    m = measure_evolution_goal(GOAL_CONSULTANT_SFT)
    assert m["goal_id"] == GOAL_CONSULTANT_SFT
    # 样本不足 min_samples → 未达
    assert m["meets"] is False


def test_sft_gate_requires_good_rate(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_TRAJECTORY_DIR", str(tmp_path / "traj"))
    monkeypatch.delenv("AIPLAT_DH_SFT_PROMOTE_SKIP_GATE", raising=False)
    # 无轨迹 → good_rate 缺测 → 不通过
    fail = evaluate_sft_promote_gate(payload={"job_id": "j1", "sample_count": 12})
    assert fail["passed"] is False
    assert fail["e5_claimed"] is False
    # 声明 good_rate 覆盖
    ok = evaluate_sft_promote_gate(
        payload={
            "job_id": "j1",
            "sample_count": 12,
            "good_rate": 0.85,
            "rated_count": 12,
        }
    )
    assert ok["passed"] is True
    assert ok["goal_id"] == GOAL_CONSULTANT_SFT


def test_goal_progress_for_kind(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    gp = goal_progress_for_kind("eval_coverage")
    assert gp["attached"] is True
    assert gp["goal_id"] == "eval.coverage.v1"
    assert gp["e5_claimed"] is False
    assert get_evolution_goal("nope") is None
