"""Bind-time unknown-asset gate + audit create recommendations."""
from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_raise_if_unknown_bindings_rejects_missing_skill(monkeypatch):
    from core.api.routers import workspace_agents as wa

    monkeypatch.setattr(
        wa,
        "_binding_catalogs",
        lambda: {
            "skills": {"summarize"},
            "tools": {"file_operations"},
            "mcp": set(),
            "agents": set(),
            "workflows": set(),
        },
    )
    with pytest.raises(HTTPException) as ei:
        wa._raise_if_unknown_bindings(skills=["no_such_skill_xyz"])
    assert ei.value.status_code == 400
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert detail.get("error") == "unknown_bindings"
    assert any(u.get("id") == "no_such_skill_xyz" for u in (detail.get("unknown") or []))


def test_raise_if_unknown_bindings_allows_known():
    from core.api.routers import workspace_agents as wa

    # Should not raise when catalogs are empty and no IDs passed
    wa._raise_if_unknown_bindings(skills=[], tools=[])


def test_missing_binding_create_issue_skill_has_brief():
    from core.api.routers.workspace_agents import _missing_binding_create_issue

    issue = _missing_binding_create_issue(
        kind="skill",
        name="need_custom_analysis",
        agent_display="产品经理",
        description="与用户对话收集需求，生成结构化PRD",
        sop_text="需要调用技能 need_custom_analysis 输出 PRD",
    )
    assert issue["category"] == "invalid_skill"
    assert issue["fix_available"] is True
    assert issue.get("fix", {}).get("type") == "remove_skill"
    assert "应具备" in (issue.get("suggestion") or "")
    assert "如何创建" in (issue.get("suggestion") or "")
    assert "解绑" in (issue.get("suggestion") or "")
    brief = issue.get("create_brief") or {}
    assert brief.get("suggested_id") == "need_custom_analysis"
    assert brief.get("must_have")
    assert brief.get("how_to_create")


@pytest.mark.asyncio
async def test_audit_invalid_skill_recommends_create(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_miss_skill"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_miss_skill\n"
        "display_name: 测试Agent\n"
        "description: 需要自定义分析能力\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_skills:\n"
        "  - totally_missing_skill_zzz\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "调用 totally_missing_skill_zzz 完成分析\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_miss_skill")
    hit = next(i for i in resp.issues if i.get("category") == "invalid_skill")
    assert hit.get("fix_available") is True
    assert hit.get("fix", {}).get("type") == "remove_skill"
    assert "应具备" in (hit.get("suggestion") or "")
    assert hit.get("create_brief", {}).get("suggested_id") == "totally_missing_skill_zzz"
