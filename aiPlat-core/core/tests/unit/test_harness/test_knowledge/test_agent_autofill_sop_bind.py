"""Unit tests for SOP-driven agent auto-fill binding."""
from __future__ import annotations

from core.api.routers.workspace_agents import _bind_from_sop, _extract_tokens_from_sop


def _catalog():
    skills = [
        {"id": "requirement_analysis", "name": "requirement_analysis", "display_name": "需求分析"},
        {"id": "summarize", "name": "summarize", "display_name": "Summarize"},
        {"id": "code", "name": "code", "display_name": "Code"},
        {"id": "knowledge_ingest_doc", "name": "knowledge_ingest_doc", "display_name": "资料导入与解析"},
        {"id": "app_page_generation", "name": "app_page_generation", "display_name": "应用页面生成"},
        {"id": "knowledge_query_doc", "name": "knowledge_query_doc", "display_name": "资料对话查询"},
    ]
    tools = [
        {"id": "file_operations", "name": "file_operations", "description": "rw"},
        {"id": "code", "name": "code", "description": "sandbox"},
        {"id": "search", "name": "search", "description": "web"},
        {"id": "web_search", "name": "web_search", "description": "web2"},
        {"id": "webfetch", "name": "webfetch", "description": "fetch"},
    ]
    name_to_id = {s["name"]: s["id"] for s in skills}
    name_to_id.update({s["display_name"]: s["id"] for s in skills})
    return skills, tools, name_to_id


def test_extract_backticks_are_intentional():
    sop = "1. 用 `requirement_analysis` 澄清\n2. 用 `file_operations` 保存"
    got = _extract_tokens_from_sop(sop)
    assert "requirement_analysis" in got["intentional"]
    assert "file_operations" in got["intentional"]


def test_ppt_bind_strips_web_and_app_page():
    skills, tools, name_to_id = _catalog()
    sop = (
        "1. 用 `requirement_analysis` 提炼主题\n"
        "2. 用 `summarize` 压缩要点\n"
        "3. 用 `code` 生成 pptx\n"
        "4. 用 `file_operations` 保存文件\n"
        "顺带提到搜索资料也不该绑 web"
    )
    bound = _bind_from_sop(
        sop,
        skill_catalog=skills,
        tool_catalog=tools,
        name_to_id=name_to_id,
        llm_needed_skills=["app_page_generation", "knowledge_query_doc"],
        llm_needed_tools=["web_search", "search", "webfetch"],
        agent_blob="PPT制作数字员工 根据描述做PPT",
    )
    assert set(bound["skills"]) <= {
        "requirement_analysis", "summarize", "code", "knowledge_ingest_doc",
    }
    assert "app_page_generation" not in bound["skills"]
    assert "knowledge_query_doc" not in bound["skills"]
    assert set(bound["tools"]) == {"file_operations", "code"}
    assert "web_search" not in bound["tools"]
    assert "search" not in bound["tools"]


def test_intentional_web_kept_when_backticked():
    skills, tools, name_to_id = _catalog()
    sop = "1. 用 `web_search` 找素材\n2. 用 `file_operations` 保存"
    bound = _bind_from_sop(
        sop,
        skill_catalog=skills,
        tool_catalog=tools,
        name_to_id=name_to_id,
        agent_blob="PPT制作",
    )
    assert "web_search" in bound["tools"]
    assert "file_operations" in bound["tools"]
