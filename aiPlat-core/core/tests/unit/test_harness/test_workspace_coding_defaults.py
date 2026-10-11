"""Workspace Execute coding closed-loop defaults (config/skill signals)."""

from __future__ import annotations

from types import SimpleNamespace

from core.schemas_builder import (
    inject_workspace_coding_defaults,
    workspace_agent_needs_coding_defaults,
)


def test_non_coding_agent_skips():
    assert (
        workspace_agent_needs_coding_defaults(
            agent_cfg={"system_prompt": "chat"},
            agent_meta={},
            skills=[],
        )
        is False
    )
    state = {"_coding_policy_profile": "off"}
    extra = inject_workspace_coding_defaults(state, agent_cfg={}, skills=[])
    assert extra == []
    assert state.get("_workspace_coding_defaults") is None
    assert state.get("_coding_policy_profile") == "off"


def test_skill_uses_file_output_opts_in(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_SANDBOX", "true")
    monkeypatch.setenv("AIPLAT_CODING_STAGE_AUTOREVIEW", "true")
    skill = SimpleNamespace(
        name="code_generation",
        _config=SimpleNamespace(metadata={"uses_file_output": True}),
        metadata=None,
    )
    assert workspace_agent_needs_coding_defaults(skills=[skill]) is True
    state: dict = {"_coding_policy_profile": "off", "_bound_skill_ids": ["code_generation"]}
    extra = inject_workspace_coding_defaults(state, skills=[skill])
    assert state.get("_workspace_coding_defaults") is True
    assert isinstance(state.get("_done_verify"), dict)
    assert state["_done_verify"].get("enabled") is True
    assert state["_done_verify"].get("require_testability") is True
    assert state.get("_sandbox") is True
    assert "autoreview" in (state.get("_bound_skill_ids") or [])
    assert "autoreview" in extra
    assert state.get("_coding_policy_profile") not in ("", None)


def test_coding_closed_loop_false_opts_out():
    skill = SimpleNamespace(
        _config=SimpleNamespace(metadata={"uses_file_output": True}),
        metadata=None,
    )
    assert (
        workspace_agent_needs_coding_defaults(
            agent_cfg={"coding_closed_loop": False},
            skills=[skill],
        )
        is False
    )


def test_coding_closed_loop_true_opts_in(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_AUTOREVIEW", "true")
    assert workspace_agent_needs_coding_defaults(agent_meta={"coding_closed_loop": True}) is True
    state: dict = {}
    inject_workspace_coding_defaults(state, agent_meta={"coding_closed_loop": True})
    assert state.get("_workspace_coding_defaults") is True


def test_coding_policy_profile_alone_does_not_opt_in():
    """karpathy_v1 without file-output must not force coding closed loop."""
    assert (
        workspace_agent_needs_coding_defaults(
            agent_cfg={"coding_policy_profile": "karpathy_v1"},
            skills=[],
        )
        is False
    )


def test_agent_uses_file_output_flag():
    assert workspace_agent_needs_coding_defaults(agent_cfg={"uses_file_output": True}) is True
