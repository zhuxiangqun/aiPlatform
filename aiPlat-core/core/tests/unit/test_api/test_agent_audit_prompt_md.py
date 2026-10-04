"""Wire prompt_auditor into Agent edit-screen AI audit."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.audit.prompt_auditor import (
    audit_agent_md,
    prompt_audit_to_issues,
)


def test_prompt_audit_flags_vague_adjective():
    rec = audit_agent_md(
        "a1",
        "# 角色\n你是工程师。\n写高质量代码，并遵循最佳实践。\n",
        frontmatter={},
    )
    issues = prompt_audit_to_issues(rec, frontmatter={})
    cats = {i["category"] for i in issues}
    assert "prompt_vague_quality_code" in cats
    assert "prompt_vague_best_practices" in cats
    vague = [i for i in issues if i["category"].startswith("prompt_vague_")]
    assert all(i["severity"] == "warning" for i in vague)
    assert all(i["field"] == "sop_body" for i in vague)


def test_prompt_audit_handoff_only_for_pipeline_agents():
    body = "# 角色\n你是助手。\n## 工作流程\n1. 接收任务\n2. 输出结果\n"
    rec = audit_agent_md("chat1", body, frontmatter={})
    trial = prompt_audit_to_issues(rec, frontmatter={})
    assert "prompt_handoff_incomplete" not in {i["category"] for i in trial}

    rec2 = audit_agent_md(
        "pipe1",
        body,
        frontmatter={"output_artifact": "code", "agent_type": "react", "phase": "development"},
    )
    pipe = prompt_audit_to_issues(
        rec2,
        frontmatter={"output_artifact": "code", "agent_type": "react", "phase": "development"},
    )
    assert "prompt_handoff_incomplete" in {i["category"] for i in pipe}


def test_prompt_audit_pass_info_when_clean():
    body = (
        "# 角色：架构师\n\n"
        "## 工作流程\n"
        "1. 读取 PRD\n"
        "2. 调用 `architecture_design`\n"
        "3. 输出 JSON\n\n"
        "## 输出要求\n"
        "必须包含 api_contracts；禁止臆造接口。\n"
        "验收：字段齐全。\n"
    )
    rec = audit_agent_md("ok1", body, frontmatter={})
    issues = prompt_audit_to_issues(rec, frontmatter={})
    cats = {i["category"] for i in issues}
    assert "prompt_md_ok" in cats
    assert not any(str(i["severity"]) == "warning" for i in issues)


def test_audit_agent_config_wires_prompt_auditor():
    """Regression: Edit Agent「AI 审核」must call prompt_auditor (was 0 callers)."""
    src = (
        Path(__file__).resolve().parents[3]
        / "api"
        / "routers"
        / "workspace_agents.py"
    ).read_text(encoding="utf-8")
    assert "from core.harness.audit import audit_agent_md, prompt_audit_to_issues" in src
    assert "prompt_audit_to_issues(" in src
    assert "audit_agent_md(" in src
    assert "class AgentAuditRequest" in src
    assert "req.sop_body" in src


@pytest.mark.asyncio
async def test_audit_prefers_draft_sop_over_disk(tmp_path, monkeypatch):
    """Edit-screen draft sop_body must drive prompt_auditor (not disk-only)."""
    agent_dir = tmp_path / ".aiplat" / "agents" / "audit_draft_sop"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_draft_sop\n"
        "agent_type: react\n"
        "status: ready\n"
        "config:\n"
        "  system_prompt: disk prompt\n"
        "---\n"
        "# 角色\n磁盘旧正文，写高质量代码，遵循最佳实践。\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )

    from core.api.routers.workspace_agents import AgentAuditRequest, audit_agent_config

    clean_draft = (
        "# 角色：架构师\n\n"
        "## 工作流程\n"
        "1. 读取 PRD\n"
        "2. 调用 skill\n"
        "3. 输出 JSON\n\n"
        "## 输出要求\n"
        "必须包含 api_contracts；禁止臆造接口。\n"
        "验收：字段齐全。\n"
    )
    resp = await audit_agent_config(
        "audit_draft_sop",
        AgentAuditRequest(sop_body=clean_draft, system_prompt="draft system prompt"),
    )
    cats = {i["category"] for i in resp.issues}
    assert "audit_draft_sop" in cats
    # Disk had vague adjectives; draft should not flag those
    assert "prompt_vague_quality_code" not in cats
    assert "prompt_vague_best_practices" not in cats
    # Draft system_prompt should satisfy missing_system_prompt
    assert "missing_system_prompt" not in cats


@pytest.mark.asyncio
async def test_audit_skips_draft_flag_when_sop_matches_disk(tmp_path, monkeypatch):
    """一键修复写入磁盘后再审：同文不当作未保存草稿。"""
    agent_dir = tmp_path / ".aiplat" / "agents" / "audit_saved_sop"
    agent_dir.mkdir(parents=True)
    body = (
        "# 角色：架构师\n\n"
        "## 工作流程\n"
        "1. 读取 PRD\n"
        "2. 调用 skill\n"
        "3. 输出 JSON\n\n"
        "## 输出要求\n"
        "必须包含 api_contracts；禁止臆造接口。\n"
        "验收：字段齐全。\n"
    )
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_saved_sop\n"
        "agent_type: react\n"
        "status: ready\n"
        "config:\n"
        "  system_prompt: saved prompt\n"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )

    from core.api.routers.workspace_agents import AgentAuditRequest, audit_agent_config

    resp = await audit_agent_config(
        "audit_saved_sop",
        AgentAuditRequest(sop_body=body, system_prompt="saved prompt"),
    )
    cats = {i["category"] for i in resp.issues}
    assert "audit_draft_sop" not in cats
