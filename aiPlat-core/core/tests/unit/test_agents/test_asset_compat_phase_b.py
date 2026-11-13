"""Phase B: Agent persona/bound/needs_binding; chat OK when binding incomplete."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.harness.maintenance.asset_compat import (
    TIER_BLOCKED,
    TIER_BOUND_READY,
    TIER_NEEDS_BINDING,
    TIER_PERSONA_READY,
    agent_compat_error,
    finalize_agent_compat,
    finalize_skill_compat,
    is_agent_chat_ok,
    is_agent_fully_usable,
    resolve_agent_dir_from_info,
)


def test_persona_ready_no_required_skills(tmp_path: Path):
    d = tmp_path / "chatty"
    d.mkdir()
    (d / "AGENT.md").write_text(
        "---\nname: chatty\ndescription: t\nrequired_skills: []\n---\nHi.\n",
        encoding="utf-8",
    )
    c = finalize_agent_compat(d)
    assert c["tier"] == TIER_PERSONA_READY
    assert c["chat_ok"] is True and c["full_ok"] is True
    assert c["ui_state"] == "现在就能用"
    assert is_agent_chat_ok(d) and is_agent_fully_usable(d)


def test_bound_ready_when_required_skill_schedulable(tmp_path: Path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    sid = skills / "helper"
    sid.mkdir()
    (sid / "SKILL.md").write_text(
        "---\nname: helper\ndescription: t\nexecution_type: prompt\n---\nHelp.\n",
        encoding="utf-8",
    )
    finalize_skill_compat(sid)

    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(skills))
    d = tmp_path / "bound-agent"
    d.mkdir()
    (d / "AGENT.md").write_text(
        "---\nname: bound-agent\ndescription: t\nrequired_skills: [helper]\n---\nGo.\n",
        encoding="utf-8",
    )
    c = finalize_agent_compat(d)
    assert c["tier"] == TIER_BOUND_READY
    assert c["chat_ok"] is True and c["full_ok"] is True


def test_needs_binding_missing_skill_still_chat_ok(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "empty-skills"))
    (tmp_path / "empty-skills").mkdir()
    d = tmp_path / "needs-bind"
    d.mkdir()
    (d / "AGENT.md").write_text(
        "---\nname: needs-bind\ndescription: t\nrequired_skills: [missing-skill]\n---\nGo.\n",
        encoding="utf-8",
    )
    c = finalize_agent_compat(d)
    assert c["tier"] == TIER_NEEDS_BINDING
    assert c["chat_ok"] is True and c["full_ok"] is False
    assert c["ui_state"] == "还差几步"
    assert is_agent_chat_ok(d) is True
    assert is_agent_fully_usable(d) is False
    err = agent_compat_error(d, agent_id="needs-bind", mode="full")
    assert err["error"] == "agent_not_usable" and err["tier"] == TIER_NEEDS_BINDING


def test_blocked_not_chat_ok(tmp_path: Path):
    d = tmp_path / "blocked-agent"
    d.mkdir()
    (d / "AGENT.md").write_text(
        "---\nname: blocked-agent\ndescription: t\nblock_reason: unsafe\n---\nNo.\n",
        encoding="utf-8",
    )
    c = finalize_agent_compat(d)
    assert c["tier"] == TIER_BLOCKED and c["chat_ok"] is False
    assert is_agent_chat_ok(d) is False


def test_pre_phase_b_dir_without_compat_fail_open(tmp_path: Path):
    old = tmp_path / "legacy-agent"
    old.mkdir()
    (old / "AGENT.md").write_text(
        "---\nname: legacy-agent\ndescription: t\n---\nHi.\n",
        encoding="utf-8",
    )
    assert not (old / "COMPAT.yaml").exists()
    assert is_agent_chat_ok(old) is True
    assert is_agent_fully_usable(old) is True


def test_resolve_agent_dir_from_info(tmp_path: Path):
    d = tmp_path / "a1"
    d.mkdir()
    info = SimpleNamespace(metadata={"filesystem": {"agent_dir": str(d)}})
    assert resolve_agent_dir_from_info(info) == d
    assert resolve_agent_dir_from_info(SimpleNamespace(metadata={})) is None


def test_execute_background_accepts_chat_lite_kwarg():
    """Regression: chat_lite must be a real kwarg (not a free var from outer scope)."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "api" / "core_facade.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in tree.body
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
        and n.name == "_execute_workspace_agent_background"
    )
    names = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    assert "chat_lite" in names
    # Call sites must pass chat_lite=
    text = src.read_text(encoding="utf-8")
    assert text.count("chat_lite=_compat_chat_lite") >= 2
    assert "if not chat_lite:" in text
