"""Unit tests for lightweight asset boundary hints."""

from __future__ import annotations

from core.apps.common.boundary_hints import (
    hints_for_agent_draft,
    hints_for_mcp_draft,
    hints_for_skill_draft,
    hints_for_tool_draft,
    normalize_raci,
)


def test_normalize_raci_empty_and_aliases():
    assert normalize_raci(None) is None
    assert normalize_raci({}) is None
    assert normalize_raci("x") is None
    out = normalize_raci(
        {
            "R": "执行准入资料收集与核验",
            "A": "供应商准入完成",
            "C": "法务, 风控",
            "I": ["采购经理", "财务"],
        }
    )
    assert out is not None
    assert out["responsible"] == "执行准入资料收集与核验"
    assert out["accountable"] == "供应商准入完成"
    assert out["consulted"] == ["法务", "风控"]
    assert out["informed"] == ["采购经理", "财务"]


def test_agent_raci_missing_hint():
    hints = hints_for_agent_draft(
        {"skills": ["a", "b"], "tools": ["t"], "mcp_ids": [], "sop_text": "x" * 300}
    )
    assert any("RACI" in h for h in hints)
    hints2 = hints_for_agent_draft(
        {
            "skills": ["a", "b"],
            "tools": ["t"],
            "mcp_ids": [],
            "sop_text": "x" * 300,
            "raci": {"responsible": "跑闭环", "accountable": "交付结果"},
        }
    )
    assert not any("RACI" in h for h in hints2)


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
