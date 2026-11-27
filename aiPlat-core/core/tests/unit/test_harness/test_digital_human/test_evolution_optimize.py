"""evolution_optimize：Phase B 最小优化闭环（草稿/沙箱，不写生产）。"""
from __future__ import annotations

import json

from core.harness.digital_human.evolution_optimize import (
    build_eval_remediation_plan,
    build_fde_completion_plan,
    knowledge_target_state_summary,
    optimize_pilot_genes_sandbox,
    propose_from_low_rated_trajectories,
)
from core.harness.digital_human.evolution_proposals import (
    STATUS_HUMAN_GATE,
    _clear_proposals_for_tests,
    list_evolution_proposals,
    propose_pilot_config,
)
from core.harness.digital_human.domain_evolution_bridge import (
    propose_eval_coverage,
    propose_fde_evolve,
    propose_knowledge_evolve,
)


def test_remediation_and_completion_plans():
    rem = build_eval_remediation_plan(["a", "b", ""])
    assert [x["capability_id"] for x in rem] == ["a", "b"]
    assert rem[0]["priority"] == 1
    comp = build_fde_completion_plan(["gate0.scope", "fde1.customer"])
    assert comp[0]["step_id"] == "gate0.scope"
    assert comp[1]["order"] == 2


def test_propose_payloads_include_plans(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    ev = propose_eval_coverage(
        coverage=0.5, threshold=0.9, missing_ids=["cap.x", "cap.y"]
    )
    assert ev["ok"] is True
    pl = ev["proposal"]["payload"]
    assert pl.get("goal_id") == "eval.coverage.v1"
    assert len(pl.get("remediation_plan") or []) == 2

    fd = propose_fde_evolve(
        reason="证据覆盖不足",
        coverage=0.5,
        missing_ids=["gate0.deploy_mode"],
    )
    assert fd["ok"] is True
    assert (fd["proposal"]["payload"].get("completion_plan") or [])[0]["step_id"] == (
        "gate0.deploy_mode"
    )

    kn = propose_knowledge_evolve(case_id="c1", domain_id="d1", reward_ema=0.91)
    assert kn["ok"] is True
    kpl = kn["proposal"]["payload"]
    assert "target_state_summary" in kpl
    assert kpl.get("fitness") == 0.91
    assert "auto_apply=false" in (kpl.get("guidance") or "")
    assert "目标态" in knowledge_target_state_summary(case_id="c1", reward_ema=0.9)


def test_low_rated_scan_creates_seed_qa(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    traj = tmp_path / "traj"
    traj.mkdir()
    monkeypatch.setenv("AIPLAT_TRAJECTORY_DIR", str(traj))
    _clear_proposals_for_tests()
    (traj / "s_bad.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "交付计划怎么建"}),
                json.dumps(
                    {
                        "role": "assistant",
                        "content": "随便点一点就行",
                        "quality": "bad",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = propose_from_low_rated_trajectories(limit=3)
    assert out["ok"] is True
    assert out["e5_claimed"] is False
    assert len(out["created"]) >= 1
    pending = list_evolution_proposals(kind="seed_qa", status=STATUS_HUMAN_GATE, limit=10)
    assert any((p.get("payload") or {}).get("source") == "low_rated_scan" for p in pending)


def test_pilot_sandbox_optimize_attaches_genes(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    opt = optimize_pilot_genes_sandbox("routing.weights.v1")
    assert opt.get("use_global_router") is False
    assert opt.get("production_write") is False
    assert opt.get("e5_claimed") is False
    r = propose_pilot_config(genome_id="routing.weights.v1")
    assert r["ok"] is True
    pl = r["proposal"]["payload"]
    assert pl.get("goal_id") == "evo.pilot_sandbox.v1"
    assert pl.get("sandbox_optimize", {}).get("use_global_router") is False
    # best_genes may be None if DE fails to rank; ok flag still present
    assert "best_genes" in pl
    assert "sandbox_optimize" in pl
