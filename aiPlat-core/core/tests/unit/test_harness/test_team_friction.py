"""T4a: friction → local learning draft tests."""
from __future__ import annotations

from core.harness.team_friction import (
    REGENERATE_THRESHOLD,
    SIGNAL_HITL_REJECT,
    SIGNAL_PRD_GATE_FAIL,
    SIGNAL_REGENERATE,
    attach_friction_cta,
    confirm_friction_share,
    list_local_learnings,
    local_learnings_dir,
    note_regenerate,
    record_friction_event,
)


def test_t4a_hitl_reject_writes_local_learning(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    r = record_friction_event(
        SIGNAL_HITL_REJECT,
        project_id="prj1",
        stage_id="arch",
        detail="need clearer API contract",
    )
    assert r["ok"] is True
    assert r["learning_id"]
    assert r["local_only"] is True
    assert (local_learnings_dir() / f"{r['learning_id']}.json").is_file()
    rows = list_local_learnings(limit=5)
    assert any(x.get("id") == r["learning_id"] for x in rows)
    # must not write under team/
    assert not (tmp_path / "team" / "learnings").exists() or not any(
        (tmp_path / "team" / "learnings").glob("*.json")
    )


def test_t4a_prd_gate_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    r = record_friction_event(SIGNAL_PRD_GATE_FAIL, project_id="p", detail="missing FR")
    assert r["ok"] and r["cta"]["signal"] == SIGNAL_PRD_GATE_FAIL


def test_t4a_regenerate_needs_confirm_and_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    r1 = note_regenerate("prj", "qa", detail="first")
    assert r1["count"] == 1
    assert not r1.get("needs_confirm")

    r2 = note_regenerate("prj", "qa", detail="second")
    assert r2["count"] >= REGENERATE_THRESHOLD
    assert r2.get("needs_confirm") is True
    assert r2["cta"]["needs_confirm"] is True

    # without confirm, record_friction_event rejects regenerate
    bad = record_friction_event(SIGNAL_REGENERATE, project_id="prj", stage_id="qa")
    assert bad["ok"] is False

    conf = confirm_friction_share(project_id="prj", stage_id="qa", detail="ok")
    assert conf["ok"] is True
    assert conf["learning_id"]

    # cooldown: further threshold hits skip
    note_regenerate("prj", "qa")
    r_cool = note_regenerate("prj", "qa")
    assert r_cool.get("skipped") == "cooldown" or r_cool["count"] < REGENERATE_THRESHOLD


def test_t4a_unknown_signal_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    r = record_friction_event("not_a_real_signal", project_id="x")
    assert r["ok"] is False


def test_t4b_schema_gate_hitl_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    r = record_friction_event("schema_gate_hitl", project_id="x", detail="gate")
    assert r["ok"] is True and r["learning_id"]


def test_attach_friction_cta_on_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    state: dict = {}
    r = record_friction_event(SIGNAL_HITL_REJECT, project_id="p", detail="x")
    attach_friction_cta(state, r["cta"])
    assert state.get("_friction_share_cta", {}).get("signal") == SIGNAL_HITL_REJECT
