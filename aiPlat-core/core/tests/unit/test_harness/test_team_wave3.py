"""T3a skill subscription + T4b friction + T5 digest unit tests."""
from __future__ import annotations

from pathlib import Path

from core.harness.team_digest import build_team_digest, record_digest_view
from core.harness.team_friction import (
    SIGNAL_REPAIR_EXHAUSTED,
    SIGNAL_SCHEMA_GATE_HITL,
    record_friction_event,
    record_schema_gate_friction,
)
from core.harness.utils.team_skill_subscription import (
    assert_required_intact,
    filter_skills_by_subscription,
    resolve_subscription_policy,
)


class _Skill:
    def __init__(self, name: str, tags=None, roles=None):
        self.name = name
        self.tags = tags or []
        self.permissions = {"roles_allowed": roles or []}


def test_t3a_required_always_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    skills = [
        _Skill("required_a", tags=["other"]),
        _Skill("optional_b", tags=["factory"]),
        _Skill("optional_c", tags=["ops"]),
    ]
    filtered = filter_skills_by_subscription(
        skills,
        required=["required_a"],
        allow_tags=["factory"],
        enabled=True,
    )
    names = [s.name for s in filtered]
    assert "required_a" in names
    assert "optional_b" in names
    assert "optional_c" not in names
    assert assert_required_intact(filtered, ["required_a"])


def test_t3a_empty_allow_passthrough(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    skills = [_Skill("a", tags=["x"]), _Skill("b", tags=["y"])]
    filtered = filter_skills_by_subscription(
        skills, required=["a"], allow_tags=[], allow_roles=[], enabled=True
    )
    assert [s.name for s in filtered] == ["a", "b"]


def test_t3a_stage_policy_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    class Stage:
        skill_allow_tags = ["media"]
        skill_allow_roles = []
        required_skills = ["core"]

    pol = resolve_subscription_policy(Stage())
    assert pol["allow_tags"] == ["media"]


def test_t4b_schema_gate_and_repair(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    state = {}
    r = record_schema_gate_friction(
        SIGNAL_SCHEMA_GATE_HITL,
        project_id="p1",
        stage_id="arch",
        detail="missing field",
        state=state,
    )
    assert r["ok"] is True and r["learning_id"]
    assert state.get("_friction_share_cta", {}).get("signal") == SIGNAL_SCHEMA_GATE_HITL

    r2 = record_friction_event(
        SIGNAL_REPAIR_EXHAUSTED, project_id="p1", detail="max rounds"
    )
    assert r2["ok"] is True and r2["learning_id"]
    learnings = list((Path(tmp_path) / "local" / "learnings").glob("*.json"))
    assert len(learnings) >= 2


def test_t5_digest_metrics_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    dig = build_team_digest(
        project_id="demo",
        project={
            "project_id": "demo",
            "phase": "done",
            "bloat_metrics": {"loc": 120, "new_files": 3, "new_deps": 1},
            "last_repair": {"repair_exhausted": True, "rounds": 2},
            "output_style": "adhd",
        },
    )
    assert dig["ok"] is True
    assert dig["privacy"] == "metrics_only"
    assert dig["bloat"]["loc"] == 120
    assert dig["repair"]["repair_exhausted"] is True
    assert "loc=120" in dig["summary"]
    v = record_digest_view("demo")
    assert v["views"] >= 1
