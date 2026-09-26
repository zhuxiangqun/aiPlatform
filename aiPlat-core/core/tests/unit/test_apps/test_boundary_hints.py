"""Unit tests for lightweight asset boundary hints."""

from __future__ import annotations

from core.apps.common.boundary_hints import (
    hints_for_agent_draft,
    hints_for_mcp_draft,
    hints_for_skill_draft,
    hints_for_tool_draft,
)


def test_agent_empty_bindings_hint():
    hints = hints_for_agent_draft({"skills": [], "tools": [], "mcp_ids": [], "sop_text": "1. hi"})
    assert any("均为空" in h for h in hints)


def test_agent_external_without_mcp():
    hints = hints_for_agent_draft(
        {"skills": ["summarize"], "tools": ["file_operations"], "mcp_ids": [], "sop_text": "x" * 300},
        description="对接飞书文档同步",
    )
    assert any("MCP" in h for h in hints)


def test_agent_no_false_mcp_on_external_content_negation():
    """「不补充外部内容」must not look like SaaS integration."""
    from core.apps.common.boundary_hints import mentions_external_system

    desc = "严格只用用户给的信息、不联网、不编造、不补充外部内容；模版可上传或内置库挑选"
    assert not mentions_external_system(desc)
    hints = hints_for_agent_draft(
        {
            "skills": ["ppt_generation"],
            "tools": ["file_operations"],
            "mcp_ids": [],
            "sop_text": "1. 不引入外部内容\n2. 生成pptx",
            "description": desc,
        },
        description=desc,
    )
    assert not any("MCP" in h for h in hints)


def test_skill_tool_like_thin_sop():
    hints = hints_for_skill_draft({"description": "读写文件", "sop": "短"}, description="读写文件")
    assert any("Tool" in h for h in hints)


def test_tool_orchestration_hint():
    hints = hints_for_tool_draft({}, description="做一个多步编排的数字员工")
    assert any("Agent" in h for h in hints)


def test_mcp_local_file_hint():
    hints = hints_for_mcp_draft({}, description="读写本地文件计算器")
    assert any("Tool" in h for h in hints)


def test_mcp_stdio_missing_command():
    hints = hints_for_mcp_draft({"transport": "stdio"}, description="外部服务")
    assert any("command" in h for h in hints)
