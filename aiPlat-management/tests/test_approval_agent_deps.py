"""Agent 上架依赖门禁：workspace lifecycle 优先于 engine skill 列表；Tool 同级。"""
from __future__ import annotations

from management.api.approval import _agent_dep_warnings


def test_workspace_enabled_skill_blocks_even_if_also_in_engine_catalog():
    """Regression: requirement_analysis in /skills must not auto-pass as listed."""
    catalog = {
        "skill_statuses": {
            "ppt_generation": "listed",
            "summarize": "listed",
            # workspace status wins (was wrongly forced to listed via engine membership)
            "requirement_analysis": "enabled",
        },
        "mcp_statuses": {},
        "tool_statuses": {"file_operations": "listed"},
    }
    agent = {
        "skills": ["ppt_generation", "requirement_analysis", "summarize"],
        "tools": ["file_operations"],
        "mcp_ids": [],
    }
    deps = _agent_dep_warnings(agent, catalog)
    assert deps == ["skill:requirement_analysis(enabled)"]


def test_engine_only_skill_treated_as_listed():
    catalog = {
        "skill_statuses": {"builtin_helper": "listed"},
        "mcp_statuses": {},
        "tool_statuses": {},
    }
    assert _agent_dep_warnings({"skills": ["builtin_helper"], "tools": [], "mcp_ids": []}, catalog) == []


def test_all_published_or_listed_ok():
    catalog = {
        "skill_statuses": {"a": "published", "b": "listed"},
        "mcp_statuses": {"m1": "listed"},
        "tool_statuses": {"file_operations": "listed"},
    }
    agent = {"skills": ["a", "b"], "tools": ["file_operations"], "mcp_ids": ["m1"]}
    assert _agent_dep_warnings(agent, catalog) == []


def test_tool_draft_blocks_agent_list_gate():
    catalog = {
        "skill_statuses": {},
        "mcp_statuses": {},
        "tool_statuses": {"file_operations": "draft"},
    }
    agent = {"skills": [], "tools": ["file_operations"], "mcp_ids": []}
    assert _agent_dep_warnings(agent, catalog) == ["tool:file_operations(draft)"]


def test_tool_published_allows_agent_list_gate():
    catalog = {
        "skill_statuses": {},
        "mcp_statuses": {},
        "tool_statuses": {"file_operations": "published"},
    }
    agent = {"skills": [], "tools": ["file_operations"], "mcp_ids": []}
    assert _agent_dep_warnings(agent, catalog) == []


def test_legacy_ok_tools_still_works_when_tool_statuses_absent():
    catalog = {
        "skill_statuses": {},
        "mcp_statuses": {},
        "ok_tools": {"file_operations"},
    }
    agent = {"skills": [], "tools": ["file_operations", "missing"], "mcp_ids": []}
    assert _agent_dep_warnings(agent, catalog) == ["tool:missing(unavailable)"]
