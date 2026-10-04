"""Shared asset audit helpers + tool audit smoke."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.management.asset_audit import (
    _mcp_evidence_metadata,
    infer_id_from_label,
    infer_mcp_allowed_tools,
    infer_mcp_endpoint,
    infer_tool_parameters_schema,
    list_workspace_agent_catalog,
    list_workspace_tool_names,
    issue,
    summarize_audit_issues,
    upsert_sop_skill_refs_appendix,
    SOP_SKILL_REFS_HEADING,
)


def test_summarize_unfixable_ignores_info():
    s = summarize_audit_issues([
        issue(severity="info", category="audit_draft_sop", field="sop_body", message="draft"),
        issue(
            severity="warning",
            category="x",
            field="f",
            message="m",
            fix={"type": "append_sop_appendix"},
        ),
    ])
    assert s["fixable"] == 1
    assert s["unfixable"] == 0
    assert s["warnings"] == 1
    assert s["info"] == 1


def test_summarize_audit_health_grades():
    assert summarize_audit_issues([])["health"] == "A"
    # Info-only must stay A (pass tips)
    assert summarize_audit_issues([
        issue(severity="info", category="ok", field="f", message="m"),
    ])["health"] == "A"
    assert summarize_audit_issues([issue(severity="warning", category="x", field="f", message="m")])["health"] == "B"
    assert summarize_audit_issues([
        issue(severity="error", category="a", field="f", message="m"),
    ])["health"] == "C"
    assert summarize_audit_issues([
        issue(severity="error", category="a", field="f", message="1"),
        issue(severity="error", category="b", field="f", message="2"),
        issue(severity="error", category="c", field="f", message="3"),
    ])["health"] == "D"


def test_role_flow_goal_appendix_clear_gates():
    from core.api.routers.workspace_agents import _audit_agent_sop_content
    from core.management.asset_audit import (
        fix_append_sop_flow,
        fix_append_sop_goal,
        fix_append_sop_role,
        upsert_sop_appendix,
    )

    thin = "短草稿\n"
    cats = {i["category"] for i in _audit_agent_sop_content(thin, skills=[], tools=[])}
    assert "sop_missing_role" in cats
    assert "sop_missing_flow" in cats
    assert "sop_missing_goal" in cats
    body = thin
    for fx in (fix_append_sop_role(), fix_append_sop_flow(), fix_append_sop_goal()):
        body = upsert_sop_appendix(body, fx["section_heading"], fx["appendix"])
    after = {i["category"] for i in _audit_agent_sop_content(body, skills=[], tools=[])}
    assert "sop_missing_role" not in after
    assert "sop_missing_flow" not in after
    assert "sop_missing_goal" not in after


def test_issue_fix_available_flag():
    with_fix = issue(
        severity="warning", category="missing_description", field="description",
        message="缺描述", fix={"type": "set_description", "description": "x"},
    )
    assert with_fix["fix_available"] is True
    assert with_fix["fix"]["type"] == "set_description"
    no_fix = issue(severity="info", category="note", field="x", message="n")
    assert no_fix["fix_available"] is False


def test_upsert_sop_skill_refs_appendix_idempotent():
    body = "# 角色：前端\n\n## 工作流程\n1. 读 api_contracts\n"
    skills = ["code_generation", "file_operations"]
    once = upsert_sop_skill_refs_appendix(body, skills)
    assert SOP_SKILL_REFS_HEADING in once
    assert "`code_generation`" in once
    assert "`file_operations`" in once
    assert once.count(SOP_SKILL_REFS_HEADING) == 1
    twice = upsert_sop_skill_refs_appendix(once, skills)
    assert twice.count(SOP_SKILL_REFS_HEADING) == 1
    assert twice.count("`code_generation`") == 1
    # steps untouched
    assert "## 工作流程" in twice
    assert "读 api_contracts" in twice


def test_upsert_strips_stacked_audit_appendices():
    from core.management.asset_audit import (
        SOP_QUALITY_HEADING,
        build_sop_quality_appendix,
        upsert_sop_appendix,
    )

    stacked = (
        "# 角色\n前端\n\n"
        f"{build_sop_quality_appendix()}\n"
        f"{build_sop_quality_appendix()}\n"
        "### 验收标准\n"
        "- 必须：输出满足约定字段/格式；关键路径可验证\n"
        "- 禁止：臆造接口、跳过验收、「跑通即合格」\n"
        "- Checklist\n"
        "  - [ ] 产物路径与字段完整\n"
        "  - [ ] 验证步骤已执行并记录结果\n"
        "\n### 约束\n"
        "- 不得省略验收；不要用模糊形容词代替可检查条件\n"
    )
    cleaned = upsert_sop_appendix(stacked, SOP_QUALITY_HEADING, build_sop_quality_appendix())
    assert cleaned.count(SOP_QUALITY_HEADING) == 1
    assert cleaned.count("以下为审核一键补齐的骨架") == 1
    assert "# 角色" in cleaned


def test_upsert_strips_stacked_role_appendices():
    """Inner ``# 角色`` must not truncate the match (一键修复叠层)."""
    from core.management.asset_audit import (
        SOP_GOAL_HEADING,
        SOP_ROLE_HEADING,
        build_sop_goal_appendix,
        build_sop_role_appendix,
        upsert_sop_appendix,
    )

    stacked = (
        "# 工程脚手架生成\n## SOP\n1. 解析\n\n"
        "# 角色\n你是本任务的执行 Agent。职责边界：只做本阶段约定工作，不越权改上游契约。\n\n"
        f"{build_sop_goal_appendix()}\n"
        f"{build_sop_goal_appendix()}\n"
        f"{build_sop_role_appendix()}\n"
        f"{build_sop_role_appendix()}\n"
    )
    cleaned = upsert_sop_appendix(stacked, SOP_ROLE_HEADING, build_sop_role_appendix())
    cleaned = upsert_sop_appendix(cleaned, SOP_GOAL_HEADING, build_sop_goal_appendix())
    assert cleaned.count(SOP_ROLE_HEADING) == 1
    assert cleaned.count(SOP_GOAL_HEADING) == 1
    assert cleaned.count("你是本任务的执行 Agent") == 1
    assert "# 工程脚手架生成" in cleaned
    assert "## SOP" in cleaned


def test_collapse_stacked_goal_skill_handoff_like_scaffold():
    """Live scaffold_agent stacked 一键修复 blocks must collapse to one each."""
    from core.management.asset_audit import (
        SOP_GOAL_HEADING,
        SOP_HANDOFF_HEADING,
        SOP_SKILL_REFS_HEADING,
        _collapse_audit_appendices,
        build_sop_goal_appendix,
        build_sop_handoff_appendix,
        build_sop_skill_refs_appendix,
        upsert_sop_appendix,
    )

    unit = (
        "# 角色\n你是本任务的执行 Agent。职责边界：只做本阶段约定工作，不越权改上游契约。\n\n"
        f"{build_sop_goal_appendix()}\n\n"
        f"{build_sop_skill_refs_appendix(['code_generation', 'file_operations'])}\n\n"
        f"{build_sop_handoff_appendix()}\n"
    )
    stacked = "# 工程脚手架生成\n\n## SOP\n1. 解析 Architecture。\n\n" + (unit * 8)
    cleaned = _collapse_audit_appendices(stacked)
    assert cleaned.count(SOP_GOAL_HEADING) == 1
    assert cleaned.count(SOP_SKILL_REFS_HEADING) == 1
    assert cleaned.count(SOP_HANDOFF_HEADING) == 1
    assert cleaned.count("你是本任务的执行 Agent") <= 1
    assert "## SOP" in cleaned
    again = upsert_sop_appendix(cleaned, SOP_HANDOFF_HEADING, build_sop_handoff_appendix())
    assert again.count(SOP_HANDOFF_HEADING) == 1
    assert again.count(SOP_GOAL_HEADING) == 1


def test_quality_appendix_clears_sop_missing_quality_keywords():
    from core.api.routers.workspace_agents import _audit_agent_sop_content
    from core.management.asset_audit import (
        SOP_QUALITY_HEADING,
        fix_append_sop_quality,
        upsert_sop_appendix,
    )

    thin = "# 角色\n你是前端。\n## 工作流程\n1. 写页面\n## 目标\n交付 UI\n"
    before = {i["category"] for i in _audit_agent_sop_content(thin, skills=[], tools=[])}
    assert "sop_missing_quality" in before
    hit = next(i for i in _audit_agent_sop_content(thin, skills=[], tools=[]) if i["category"] == "sop_missing_quality")
    assert hit.get("fix_available") is True
    assert hit["fix"]["type"] == "append_sop_appendix"

    fx = fix_append_sop_quality()
    patched = upsert_sop_appendix(thin, SOP_QUALITY_HEADING, fx["appendix"])
    after = {i["category"] for i in _audit_agent_sop_content(patched, skills=[], tools=[])}
    assert "sop_missing_quality" not in after


def test_handoff_appendix_satisfies_prompt_auditor():
    from core.harness.audit.prompt_auditor import audit_agent_md, prompt_audit_to_issues
    from core.management.asset_audit import (
        SOP_HANDOFF_HEADING,
        fix_append_sop_handoff,
        upsert_sop_appendix,
    )

    body = "# 角色\n流水线助手。\n## 工作流程\n1. 做完交接\n"
    fm = {"output_artifact": "ui", "agent_type": "react", "phase": "frontend"}
    before = prompt_audit_to_issues(audit_agent_md("fe", body, frontmatter=fm), frontmatter=fm)
    assert "prompt_handoff_incomplete" in {i["category"] for i in before}
    handoff_issue = next(i for i in before if i["category"] == "prompt_handoff_incomplete")
    assert handoff_issue.get("fix_available") is True
    assert handoff_issue["fix"]["type"] == "append_sop_appendix"

    fx = fix_append_sop_handoff()
    patched = upsert_sop_appendix(body, SOP_HANDOFF_HEADING, fx["appendix"])
    assert all(k in patched for k in ("做了什么", "产出物在哪", "如何验证", "已知问题", "下一步"))
    after = prompt_audit_to_issues(audit_agent_md("fe", patched, frontmatter=fm), frontmatter=fm)
    assert "prompt_handoff_incomplete" not in {i["category"] for i in after}


@pytest.mark.asyncio
async def test_audit_tool_missing_description(monkeypatch):
    class _Cfg:
        parameters = {"type": "object", "properties": {}}
        metadata = {"provenance": {}}
        description = ""

    class _Tool:
        _config = _Cfg()

        def get_description(self):
            return ""

    class _Reg:
        def get(self, name):
            return _Tool() if name == "audit_tool_x" else None

    monkeypatch.setattr("core.apps.tools.base.get_tool_registry", lambda: _Reg())
    monkeypatch.setattr("core.apps.tools.lifecycle.get_tool_status", lambda *a, **k: "draft")

    from core.api.routers.tools import audit_tool_config

    resp = await audit_tool_config("audit_tool_x")
    cats = {i["category"] for i in resp["issues"]}
    assert "missing_description" in cats
    assert "not_listed" in cats
    assert resp["summary"]["health"] in ("B", "C", "D")


def test_infer_tool_parameters_from_execute_source():
    src = '''
async def execute(self, query: str, limit: int = 10):
    return query
'''
    schema = infer_tool_parameters_schema(object(), source=src)
    assert schema is not None
    assert "query" in schema["properties"]
    assert "limit" in schema["properties"]
    assert schema["properties"]["limit"]["type"] == "integer"
    assert "query" in schema["required"]
    assert "limit" not in schema["required"]


def test_infer_tool_parameters_from_tool_def():
    src = '''
TOOL_DEF = {
    "name": "t",
    "parameters": {
        "type": "object",
        "properties": {"file": {"type": "string"}},
        "required": ["file"],
    },
}
'''
    schema = infer_tool_parameters_schema(object(), source=src)
    assert schema["properties"]["file"]["type"] == "string"


def test_infer_tool_parameters_no_invented_input():
    assert infer_tool_parameters_schema(object(), source="def execute(self, params):\n    pass\n") is None


def test_infer_tool_parameters_from_params_get():
    src = '''
async def execute(self, params):
    file_path = str(params.get("file_path") or "").strip()
    dpi = int(params.get("dpi") or 240)
    if not file_path:
        return {"error": "file_path_required"}
'''
    schema = infer_tool_parameters_schema(object(), source=src)
    assert schema is not None
    assert "file_path" in schema["properties"]
    assert schema["properties"]["dpi"]["type"] == "integer"
    assert "file_path" in schema["required"]
    assert "input" not in schema["properties"]


def test_kb_ingest_declares_file_path_schema():
    from core.apps.tools.kb_tools import KBIngestTool, KBQueryTool

    ingest = KBIngestTool()
    q = KBQueryTool()
    assert "file_path" in (ingest._config.parameters.get("properties") or {})
    assert "file_path" in (ingest._config.parameters.get("required") or [])
    assert "question" in (q._config.parameters.get("properties") or {})
    inferred = infer_tool_parameters_schema(ingest)
    assert inferred and "file_path" in inferred["properties"]


def test_infer_mcp_uses_env_and_command_not_placeholder():
    ev = infer_mcp_endpoint(
        name="video_mcp",
        transport="sse",
        url="",
        command="",
        metadata={},
        env={"AIPLAT_MCP_VIDEO_MCP_URL": "https://mcp.example.net/sse"},
    )
    assert ev.get("url") == "https://mcp.example.net/sse"
    ev2 = infer_mcp_endpoint(
        name="x", transport="sse", url="", command="/usr/bin/npx", metadata={}, env={},
    )
    assert ev2.get("transport") == "stdio"
    assert "url" not in ev2
    ev3 = infer_mcp_endpoint(
        name="x", transport="sse", url="", command="",
        metadata={"url": "http://127.0.0.1:8080"}, env={},
    )
    assert ev3.get("url") is None
    assert ev3.get("transport") is None
    ev4 = infer_mcp_endpoint(
        name="x",
        transport="sse",
        url="",
        command="",
        metadata={"description": "内部 MCP 见 https://mcp.corp.internal/v1"},
        env={},
    )
    assert ev4.get("url") == "https://mcp.corp.internal/v1"


def test_infer_mcp_from_runtime_description_and_env_command():
    class _Srv:
        description = "文档: https://mcp.corp.internal/sse"
        metadata = {}
        url = ""
        command = ""

    md = _mcp_evidence_metadata(_Srv())
    ev = infer_mcp_endpoint(
        name="docs",
        transport="sse",
        url="",
        command="",
        metadata=md,
        description=_Srv.description,
        env={},
    )
    assert ev.get("url") == "https://mcp.corp.internal/sse"
    evc = infer_mcp_endpoint(
        name="foo",
        transport="stdio",
        url="",
        command="",
        metadata={},
        env={"AIPLAT_MCP_FOO_COMMAND": "/opt/mcp/run.sh"},
    )
    assert evc.get("command") == "/opt/mcp/run.sh"
    evp = infer_mcp_endpoint(
        name="foo",
        transport="stdio",
        url="",
        command="",
        metadata={"command": "python3"},
        env={},
    )
    assert "command" not in evp


def test_infer_mcp_allowed_tools_from_policy_and_discover_cache():
    assert infer_mcp_allowed_tools(
        policy_data={"allowed_tools": ["read_file", "write_file"]},
    ) == ["read_file", "write_file"]
    assert infer_mcp_allowed_tools(
        metadata={"last_discovered_tools": [{"name": "search"}, {"name": "fetch"}]},
    ) == ["search", "fetch"]
    assert infer_mcp_allowed_tools(yaml_data={"tools": ["only_a"]}) == ["only_a"]
    assert infer_mcp_allowed_tools() == []


def test_infer_tool_parameters_from_io_clause():
    class _T:
        def get_description(self):
            return "上传文件。入参：file_path、tenant_id"

    schema = infer_tool_parameters_schema(_T())
    assert schema is not None
    assert "file_path" in schema["properties"]
    assert "tenant_id" in schema["properties"]


def test_infer_id_from_label_exact_slug_alias_unique_contain():
    assert infer_id_from_label("pm_agent", ["pm_agent", "eval_engineer"]) == "pm_agent"
    assert infer_id_from_label("PM Agent", ["pm_agent"]) == "pm_agent"
    assert infer_id_from_label("产品经理", ["pm_agent"], aliases={"产品经理": "pm_agent"}) == "pm_agent"
    assert infer_id_from_label("run pm_agent stage", ["pm_agent"]) == "pm_agent"
    assert infer_id_from_label("评估", ["eval_a", "eval_b"]) is None
    assert infer_id_from_label("A", ["eval_engineer", "pm_agent"]) is None
    assert infer_id_from_label("产品经理", ["pm_agent", "eval_engineer"], aliases={"评估工程师": "eval_engineer"}) is None


def test_list_workspace_agent_and_tool_catalog(tmp_path: Path):
    ag = tmp_path / "agents" / "pm_agent"
    ag.mkdir(parents=True)
    (ag / "AGENT.md").write_text(
        "---\nname: pm_agent\ndisplay_name: 产品经理\n---\n# x\n",
        encoding="utf-8",
    )
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "square_calc.py").write_text(
        'TOOL_DEF = {"name": "square_calc", "description": "x"}\n',
        encoding="utf-8",
    )
    cat = list_workspace_agent_catalog(tmp_path)
    assert cat["pm_agent"] == "产品经理"
    assert "square_calc" in list_workspace_tool_names(tmp_path)


def test_kb_tools_registered_in_server():
    src = (Path(__file__).resolve().parents[3] / "server.py").read_text(encoding="utf-8")
    assert "KBIngestTool" in src
    assert "KBQueryTool" in src
