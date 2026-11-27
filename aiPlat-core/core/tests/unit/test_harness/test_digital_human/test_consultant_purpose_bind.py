"""consultant_purpose_bind：回执落盘 + env 门控。"""
from __future__ import annotations

from core.harness.digital_human.consultant_purpose_bind import (
    active_consultant_bind_meta,
    _clear_purpose_bind_for_tests,
    load_purpose_bind,
    purpose_bind_brief_line,
    purpose_bind_enabled,
    write_purpose_bind,
)
from core.harness.digital_human.evolution_proposals import (
    STATUS_APPLIED,
    STATUS_HUMAN_GATE,
    _clear_proposals_for_tests,
    decide_evolution_proposal,
    list_evolution_proposals,
    maybe_propose_purpose_bind,
)


def test_receipt_default_env_off(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_DH_PURPOSE_BIND", raising=False)
    _clear_purpose_bind_for_tests()
    assert purpose_bind_enabled() is False
    w = write_purpose_bind(model="demo-ft", purpose="auto", job_id="j1")
    assert w["ok"] is True
    assert w["production_model_changed"] is False
    assert load_purpose_bind()["model"] == "demo-ft"
    active = active_consultant_bind_meta()
    assert active["bind_active"] is False
    assert active["reason"] == "env_off"
    assert "回执" in purpose_bind_brief_line() or "绑定" in purpose_bind_brief_line()


def test_env_on_activates_consultant_meta(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_DH_PURPOSE_BIND", "1")
    _clear_purpose_bind_for_tests()
    write_purpose_bind(model="demo-ft", purpose="chat", job_id="j2")
    active = active_consultant_bind_meta()
    assert active["bind_active"] is True
    assert active["model"] == "demo-ft"
    assert active["model_purpose"] == "chat"
    assert active["production_model_changed"] is False
    assert active["feeds_global_routing"] is False


def test_purpose_bind_proposal_apply(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_DH_PURPOSE_BIND", raising=False)
    _clear_proposals_for_tests()
    _clear_purpose_bind_for_tests()
    r = maybe_propose_purpose_bind(job_id="job_pb1", model="m-ft", purpose="auto")
    assert r["ok"] is True
    assert r["proposal"]["kind"] == "purpose_bind"
    assert r["proposal"]["status"] == STATUS_HUMAN_GATE
    decided = decide_evolution_proposal(
        decision="approve",
        proposal_id=r["proposal"]["id"],
    )
    assert decided["ok"] is True
    assert decided["production_model_changed"] is False
    assert decided["proposal"]["status"] == STATUS_APPLIED
    assert load_purpose_bind()["job_id"] == "job_pb1"
    # 防抖
    r2 = maybe_propose_purpose_bind(job_id="job_pb1", model="m-ft")
    assert r2["ok"] is False
    assert list_evolution_proposals(kind="purpose_bind", limit=5)


def test_propose_from_latest_sft(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    from core.harness.digital_human.evolution_proposals import (
        create_evolution_proposal,
        propose_purpose_bind_from_latest,
    )

    # 模拟已 APPLIED 的 sft_promote（跳过 apply，直接改状态不方便；改用 create + 手动写 status）
    created = create_evolution_proposal(
        kind="sft_promote",
        title="sft-done",
        payload={"job_id": "job_from_latest", "base_model": "bm"},
        status=STATUS_APPLIED,
    )
    assert created["ok"]
    # create 默认 HUMAN_GATE；重写为 APPLIED
    from core.harness.digital_human.evolution_proposals import _rewrite_all, list_evolution_proposals as _list

    rows = list(_list(limit=50))
    # list is newest-first; rewrite store with APPLIED
    for row in rows:
        if row.get("id") == created["proposal"]["id"]:
            row["status"] = STATUS_APPLIED
    # list returns reversed view — need full store rewrite from file order
    from core.harness.digital_human import evolution_proposals as ep

    path = ep._store_path()
    import json

    all_rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("id") == created["proposal"]["id"]:
            obj["status"] = STATUS_APPLIED
        all_rows.append(obj)
    ep._rewrite_all(all_rows)

    out = propose_purpose_bind_from_latest()
    assert out["ok"] is True
    assert out["proposal"]["kind"] == "purpose_bind"
    assert out["proposal"]["payload"]["job_id"] == "job_from_latest"
