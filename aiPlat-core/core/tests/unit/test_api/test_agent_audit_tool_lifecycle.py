"""Agent AI audit must flag bound tools that are registered but not listed."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_audit_listed_engine_tool_not_flagged_missing(tmp_path, monkeypatch):
    """Regression: known+listed tools must not fall through to invalid_tool/create."""
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_tool_ok"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_tool_ok\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_tools:\n"
        "  - routed_retrieve\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: ["routed_retrieve"]})(),
    )
    monkeypatch.setattr(
        "core.apps.tools.lifecycle.get_tool_status",
        lambda *a, **k: "listed",
    )
    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_tool_ok")
    cats = {i["category"] for i in resp.issues}
    assert "invalid_tool" not in cats
    assert "tool_not_listed" not in cats
    assert "tool_binding_ok" in cats
    hit = next(i for i in resp.issues if i["category"] == "tool_binding_ok")
    assert hit["severity"] == "info"
    assert "routed_retrieve" in str(hit.get("current") or hit.get("message") or "")
    assert resp.summary.get("health") == "A" or resp.summary.get("errors", 0) == 0


@pytest.mark.asyncio
async def test_audit_flags_registered_but_unlisted_tool(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_tool_gate"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_tool_gate\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_tools:\n"
        "  - routed_retrieve\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    class _Reg:
        def list_tools(self):
            return ["routed_retrieve", "file_operations"]

    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: _Reg(),
    )
    # Default lifecycle = draft (empty store under AIPLAT_HOME)
    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_tool_gate")
    cats = {i["category"] for i in resp.issues}
    assert "tool_not_listed" in cats
    hit = next(i for i in resp.issues if i["category"] == "tool_not_listed")
    assert hit["current"] == "routed_retrieve"
    assert hit["severity"] == "error"
    assert hit.get("fix_available") is True
    assert (hit.get("fix") or {}).get("type") == "remove_tool"
    assert (hit.get("fix") or {}).get("apply_all") is False
    assert "不会代提" in (hit.get("suggestion") or "") or "人工" in (hit.get("suggestion") or "")
    assert "解绑" in (hit.get("suggestion") or "")
    assert resp.summary["health"] in ("C", "D")


@pytest.mark.asyncio
async def test_audit_allows_engine_only_skill_as_info(tmp_path, monkeypatch):
    """Engine skills are first-class — bind without workspace mirror; info only, not error."""
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_engine_only_skill"
    agent_dir.mkdir(parents=True)
    (home / "skills").mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_engine_only_skill\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_skills:\n"
        "  - architecture_design\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    class _Reg:
        def list_tools(self):
            return []

    monkeypatch.setattr("core.apps.tools.base.get_tool_registry", lambda: _Reg())
    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_engine_only_skill")
    cats = {i["category"] for i in resp.issues}
    assert "skill_not_in_workspace_library" not in cats
    assert "skill_not_listed" not in cats
    assert "engine_skill_binding" in cats
    hits = [i for i in resp.issues if i["category"] == "engine_skill_binding"]
    assert len(hits) == 1
    assert hits[0]["severity"] == "info"
    assert "architecture_design" in str(hits[0].get("current") or hits[0].get("message") or "")
    # Info-only must not lower health below A
    assert resp.summary.get("errors", 0) == 0
    assert resp.summary.get("warnings", 0) == 0
    assert resp.summary.get("health") == "A"
    assert not any(
        i["severity"] == "error" and i["category"] in (
            "skill_not_in_workspace_library",
            "skill_not_listed",
            "invalid_skill",
            "engine_skill_binding",
        )
        for i in resp.issues
    )


@pytest.mark.asyncio
async def test_audit_flags_workspace_skill_not_listed(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_skill_gate"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_skill_gate\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_skills:\n"
        "  - requirement_analysis\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    skill_dir = home / "skills" / "requirement_analysis"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: requirement_analysis\n"
        "display_name: 需求分析\n"
        "status: enabled\n"
        "execution_type: prompt\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    class _Reg:
        def list_tools(self):
            return []

    monkeypatch.setattr("core.apps.tools.base.get_tool_registry", lambda: _Reg())
    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_skill_gate")
    cats = {i["category"] for i in resp.issues}
    assert "skill_not_listed" in cats
    hit = next(i for i in resp.issues if i["category"] == "skill_not_listed")
    assert hit["current"] == "requirement_analysis"
    assert "enabled" in hit["message"]
    assert hit.get("fix_available") is True
    assert (hit.get("fix") or {}).get("type") == "remove_skill"
    assert (hit.get("fix") or {}).get("apply_all") is False
    assert "上架" in (hit.get("suggestion") or "")
    assert "解绑" in (hit.get("suggestion") or "")
    assert "不会代提" in (hit.get("suggestion") or "") or "人工" in (hit.get("suggestion") or "")


@pytest.mark.asyncio
async def test_audit_passes_listed_workspace_skill(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_skill_ok"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_skill_ok\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_skills:\n"
        "  - requirement_analysis\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    skill_dir = home / "skills" / "requirement_analysis"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: requirement_analysis\n"
        "display_name: 需求分析\n"
        "status: listed\n"
        "execution_type: prompt\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    class _Reg:
        def list_tools(self):
            return []

    monkeypatch.setattr("core.apps.tools.base.get_tool_registry", lambda: _Reg())
    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_skill_ok")
    assert not any(i["category"] == "skill_not_listed" for i in resp.issues)
    assert not any(i["category"] == "invalid_skill" for i in resp.issues)
