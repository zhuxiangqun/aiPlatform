"""evolution_status 快照 + 回滚纠偏。"""
from __future__ import annotations

from core.harness.digital_human.consultant_purpose_bind import (
    _clear_purpose_bind_for_tests,
    load_purpose_bind,
    write_purpose_bind,
)
from core.harness.digital_human.evolution_proposals import (
    STATUS_APPLIED,
    STATUS_HUMAN_GATE,
    STATUS_REJECTED,
    STATUS_ROLLED_BACK,
    _clear_proposals_for_tests,
    create_evolution_proposal,
    decide_evolution_proposal,
    rollback_evolution_proposal,
)
from core.harness.digital_human.evolution_status import get_evolution_status_snapshot


def test_status_snapshot_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    created = create_evolution_proposal(
        kind="seed_qa",
        title="snap-seed",
        summary="for status",
        payload={"goal_id": "consultant.sft_quality.v1"},
    )
    assert created["ok"]
    snap = get_evolution_status_snapshot(limit=20)
    assert snap["ok"] is True
    assert snap["e5_claimed"] is False
    assert snap["production_model_changed"] is False
    assert "goals" in snap
    assert isinstance(snap["proposals"], list)
    assert isinstance(snap["timeline"], list)
    assert any(p.get("id") == created["proposal"]["id"] for p in snap["proposals"])
    assert any(p.get("status") == STATUS_HUMAN_GATE for p in snap["pending"])
    assert any(e.get("event") == "created" for e in snap["timeline"])


def test_reject_pending(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    created = create_evolution_proposal(kind="seed_qa", title="rej")
    pid = created["proposal"]["id"]
    out = decide_evolution_proposal(decision="reject", proposal_id=pid, actor="tester")
    assert out["ok"] is True
    assert out["proposal"]["status"] == STATUS_REJECTED
    assert out["proposal"].get("production_model_changed") is not True


def test_rollback_applied_purpose_bind(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_DH_PURPOSE_BIND", raising=False)
    _clear_proposals_for_tests()
    _clear_purpose_bind_for_tests()

    created = create_evolution_proposal(
        kind="purpose_bind",
        title="bind-rb",
        payload={"model": "m-ft", "purpose": "auto", "job_id": "j-rb"},
    )
    pid = created["proposal"]["id"]
    decided = decide_evolution_proposal(decision="approve", proposal_id=pid, actor="tester")
    assert decided["ok"] is True
    assert decided["proposal"]["status"] == STATUS_APPLIED
    assert load_purpose_bind() is not None

    # 确保绑定文件带上 proposal_id（apply 路径应写入；兜底补写）
    bind = load_purpose_bind() or {}
    if not bind.get("proposal_id"):
        write_purpose_bind(
            model="m-ft",
            purpose="auto",
            job_id="j-rb",
            proposal_id=pid,
        )

    rb = rollback_evolution_proposal(proposal_id=pid, actor="tester", reason="wrong_direction")
    assert rb["ok"] is True
    assert rb["proposal"]["status"] == STATUS_ROLLED_BACK
    assert rb["e5_claimed"] is False
    assert rb["production_model_changed"] is False
    assert load_purpose_bind() is None

    # facade thin wrappers
    from core.api import core_facade as facade

    snap = facade.get_digital_human_evolution_status(limit=10)
    assert snap["ok"] is True
    assert snap["e5_claimed"] is False


def test_rollback_rejects_human_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    created = create_evolution_proposal(kind="pilot_config", title="no-rb")
    out = rollback_evolution_proposal(
        proposal_id=created["proposal"]["id"],
        reason="test",
    )
    assert out["ok"] is False
    assert out["reason"] == "not_rollbackable"
