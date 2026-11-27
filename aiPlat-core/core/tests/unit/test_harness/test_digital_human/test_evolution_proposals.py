"""evolution_proposals：状态机、有界应用、诚实锁。"""
from __future__ import annotations

from core.harness.digital_human.evolution_proposals import (
    STATUS_APPLIED,
    STATUS_APPROVED,
    STATUS_HUMAN_GATE,
    STATUS_REJECTED,
    _clear_proposals_for_tests,
    create_evolution_proposal,
    decide_evolution_proposal,
    evolution_proposals_brief_line,
    list_evolution_proposals,
    maybe_propose_from_feedback,
    maybe_propose_sft_promote,
    parse_evolution_decide_utterance,
    pending_human_gate_count,
    try_handle_evolution_utterance,
)


def test_feedback_seed_qa_and_approve(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    r = maybe_propose_from_feedback(
        rating="bad",
        correction="交付计划不需要先诊断",
        tenant_id="default",
        session_id="dh_t1",
    )
    assert r["ok"] is True
    prop = r["proposal"]
    assert prop["kind"] == "seed_qa"
    assert prop["status"] == STATUS_HUMAN_GATE
    assert pending_human_gate_count() == 1
    assert "待批" in evolution_proposals_brief_line()

    decided = decide_evolution_proposal(decision="approve", proposal_id=prop["id"])
    assert decided["ok"] is True
    assert decided["production_model_changed"] is False
    assert decided["apply_result"]["production_model_changed"] is False
    assert decided["proposal"]["status"] == STATUS_APPLIED
    seed = tmp_path / "digital_human" / "approved_seed_qa.jsonl"
    assert seed.is_file()
    assert "交付计划" in seed.read_text(encoding="utf-8")


def test_sft_promote_honesty_lock(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_TRAJECTORY_DIR", str(tmp_path / "traj"))
    monkeypatch.delenv("AIPLAT_DH_SFT_PROMOTE_SKIP_GATE", raising=False)
    monkeypatch.setattr(
        "core.harness.digital_human.evolution_goals.measure_curated_feedback_rate",
        lambda: {
            "ok": True,
            "baseline_missing": False,
            "good_rate": 0.9,
            "good": 9,
            "bad": 1,
            "rated": 10,
        },
    )
    _clear_proposals_for_tests()
    r = maybe_propose_sft_promote(
        {
            "submitted": True,
            "job_id": "job_abc123",
            "dataset_id": "ds1",
            "provider": "local",
            "base_model": "dummy",
            "converted_count": 12,
        }
    )
    assert r["ok"] is True
    assert r["proposal"]["payload"].get("goal_id") == "consultant.sft_quality.v1"
    pid = r["proposal"]["id"]
    decided = decide_evolution_proposal(decision="approve", proposal_id=pid)
    assert decided["ok"] is True
    assert decided["production_model_changed"] is False
    assert decided["apply_result"]["production_model_changed"] is False
    assert decided["apply_result"].get("applied") is True
    assert decided["apply_result"].get("eval_gate", {}).get("passed") is True
    assert decided["proposal"]["status"] == STATUS_APPLIED
    assert "/infra/finetune" in str(decided["apply_result"].get("guidance") or "")
    # 链式 purpose_bind 待批
    chained = decided["apply_result"].get("purpose_bind_proposal") or {}
    assert chained.get("ok") is True
    assert chained.get("proposal", {}).get("kind") == "purpose_bind"
    # 同 job 防抖
    r2 = maybe_propose_sft_promote(
        {"submitted": True, "job_id": "job_abc123", "dataset_id": "ds1"}
    )
    assert r2["ok"] is False
    assert r2["reason"] == "already_proposed"


def test_sft_promote_gate_blocks_applied_without_job(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_DH_SFT_PROMOTE_SKIP_GATE", raising=False)
    _clear_proposals_for_tests()
    created = create_evolution_proposal(
        kind="sft_promote",
        title="缺 job",
        payload={"guidance": "x", "sample_count": 12},
    )
    assert created["ok"]
    decided = decide_evolution_proposal(
        decision="approve",
        proposal_id=created["proposal"]["id"],
    )
    assert decided["ok"] is True
    assert decided["apply_result"].get("applied") is False
    assert decided["apply_result"].get("reason") == "eval_gate_failed"
    assert decided["proposal"]["status"] == STATUS_APPROVED
    assert decided["production_model_changed"] is False


def test_reject_and_utterance(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    create_evolution_proposal(
        kind="habit_promotion",
        title="巩固有用",
        summary="t",
    )
    assert parse_evolution_decide_utterance("批准第1条")["decision"] == "approve"
    handled = try_handle_evolution_utterance("拒绝第1条")
    assert handled and handled["ok"] is True
    assert list_evolution_proposals(status=STATUS_REJECTED, limit=5)
    assert pending_human_gate_count() == 0


def test_facade_decide_never_changes_model(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    from core.api import core_facade as facade

    created = facade.create_digital_human_evolution_proposal(
        kind="sft_promote",
        title="facade-sft",
        payload={"job_id": "j9", "guidance": "去 /infra/finetune"},
    )
    assert created["ok"]
    out = facade.decide_digital_human_evolution_proposal(
        decision="approve",
        proposal_id=created["proposal"]["id"],
    )
    assert out["ok"]
    assert out["production_model_changed"] is False


def test_pilot_config_sandbox_bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    from core.harness.digital_human.evolution_proposals import (
        evo_pilot_candidates_brief_line,
        ensure_pilot_config_proposals,
        propose_pilot_config,
    )
    from core.harness.evo_compute.candidate_ledger import clear_ledger_for_tests

    clear_ledger_for_tests()
    ens = ensure_pilot_config_proposals()
    assert ens["ok"]
    assert len(ens["created"]) == 3
    ens2 = ensure_pilot_config_proposals()
    assert ens2["created"] == []

    r = propose_pilot_config(genome_id="routing.weights.v1")
    assert r["ok"] is False
    assert r["reason"] == "already_pending"

    pending = list_evolution_proposals(kind="pilot_config", status=STATUS_HUMAN_GATE, limit=10)
    assert len(pending) == 3
    assert all(p.get("payload", {}).get("goal_id") == "evo.pilot_sandbox.v1" for p in pending)
    decided = decide_evolution_proposal(decision="approve", proposal_id=pending[0]["id"])
    assert decided["ok"] is True
    assert decided["production_model_changed"] is False
    ar = decided["apply_result"]
    assert ar.get("production_write") is False
    assert ar.get("use_global_router") is False
    assert ar.get("ledger", {}).get("ok") is True
    assert "试点" in evo_pilot_candidates_brief_line() or "台账" in evo_pilot_candidates_brief_line()
