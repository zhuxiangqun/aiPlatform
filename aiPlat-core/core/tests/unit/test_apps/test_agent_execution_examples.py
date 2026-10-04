"""Agent execution example chips should be role-aware (not one-liner smoke)."""

from __future__ import annotations

from core.management.execution_examples import build_agent_task_examples, examples_are_generic


def _assert_rich(ex):
    assert len(ex) >= 2
    blob = "\n".join(e["content"] for e in ex)
    assert "按本 Agent 的职责做一次冒烟验证" not in blob
    assert not examples_are_generic(ex)
    return blob


def test_pm_agent_examples_are_rich_prd_scenarios():
    ex = build_agent_task_examples(
        display_name="产品经理",
        description="与用户对话收集需求，生成结构化PRD",
        skill_ids=["requirement_analysis", "chitchat"],
        tool_ids=["knowledge_retrieve"],
    )
    blob = _assert_rich(ex)
    assert "PRD" in blob or "prd" in blob.lower()
    assert "澄清" in blob or "追问" in blob
    # Hard self-checks for the inspection PRD smoke case
    assert "不能传到公网" in blob or "不上公网" in blob
    assert "API" in blob and ("待确认" in blob or "未开放" in blob)
    assert "硬性自检" in blob
    assert "PRD_READY" in blob  # instruction forbids emitting the marker


def test_architect_qa_coder_research_examples():
    arch = build_agent_task_examples(
        display_name="系统架构师",
        description="根据PRD完成系统架构设计",
        skill_ids=["architecture_design"],
    )
    assert "架构" in _assert_rich(arch)

    qa = build_agent_task_examples(
        display_name="测试经理",
        description="测试用例设计",
        skill_ids=["test_case_generation"],
    )
    assert "用例" in _assert_rich(qa)

    coder = build_agent_task_examples(
        display_name="程序员",
        description="根据 PRD + 架构设计产出代码",
        skill_ids=["code_generation", "file_operations"],
    )
    coder_blob = _assert_rich(coder)
    assert "api" in coder_blob.lower() or "API" in coder_blob

    research = build_agent_task_examples(
        display_name="自动调研助手",
        description="给定话题做多源调研并输出报告",
        skill_ids=["last30days", "webfetch", "browser"],
    )
    blob = _assert_rich(research)
    assert "调研" in blob or "来源" in blob
    # must not collapse to site-tester one-liner
    assert "技能上架" in blob or "来源" in blob


def test_eval_engineer_examples_use_target_agent_id():
    ex = build_agent_task_examples(
        display_name="评估工程师",
        description="基于 Amazon Eval Agent 论文方法，自动为 Agent 生成评估代码",
        skill_ids=[
            "eval_code_generator",
            "code_review",
            "test_case_generation",
            "code-hygiene",
        ],
    )
    blob = _assert_rich(ex)
    titles = "\n".join(e["title"] for e in ex)
    assert "target_agent_id" in blob
    assert "qa_agent" in blob
    assert "eval_code_generator" in blob or "eval_metric" in blob
    assert "巡检报障·用例集" not in titles
    assert "按 agent_id 评估" in titles


def test_test_executor_examples_are_runnable_cases_not_product_brief():
    ex = build_agent_task_examples(
        display_name="测试执行器",
        description="读取测试经理产出的 test_cases，逐条执行对话验证并产出通过/失败报告",
        skill_ids=["test_executor"],
    )
    blob = _assert_rich(ex)
    titles = "\n".join(e["title"] for e in ex)
    assert "test_cases" in blob
    assert "SMK-001" in blob
    assert "PLT-001" in blob
    assert "platform.ssrf_block" in blob
    assert "API-001" not in blob  # bare skill_invoke without skill name removed
    assert "复杂冒烟" not in blob
    assert "钉钉 API 未开放" not in blob
    assert "带 test_cases" in titles
    assert "缺用例应阻断" in titles
    empty = next(e for e in ex if "阻断" in e["title"])
    import json as _json

    payload = _json.loads(empty["content"])
    assert payload.get("test_cases") == []


def test_architect_not_misclassified_by_prd_in_description():
    ex = build_agent_task_examples(
        display_name="系统架构师",
        description="根据PRD完成系统架构设计",
        skill_ids=["architecture_design", "autoreview"],
    )
    blob = _assert_rich(ex)
    assert "架构" in blob
    assert "巡检报障·PRD 草稿" not in "\n".join(e["title"] for e in ex)


def test_legacy_smoke_marked_generic():
    assert examples_are_generic(
        [
            {
                "title": "产品经理（文本）",
                "content": "任务背景：x\n请完成以下任务：\n按本 Agent 的职责做一次冒烟验证（说明你做了什么、结果如何）。",
            }
        ]
    )


def test_pm_examples_do_not_require_code_generation():
    ex = build_agent_task_examples(
        display_name="产品经理",
        description="与用户对话收集需求，生成结构化PRD",
        skill_ids=["requirement_analysis"],
    )
    blob = _assert_rich(ex)
    assert "code_generation" not in blob
    assert "## FILE:" not in blob
    assert "ReportFaultPage" not in blob


def test_frontend_engineer_examples_are_typescript_not_fastapi():
    ex = build_agent_task_examples(
        display_name="前端工程师",
        description="根据 Architecture 中的 api_contracts 生成前端代码",
        skill_ids=["code_generation", "autoreview", "file_operations"],
    )
    blob = _assert_rich(ex)
    assert "TypeScript" in blob or "*.ts" in blob or "tsx" in blob.lower()
    assert "Pydantic" not in blob
    assert "FastAPI" not in blob or "禁止 Python/FastAPI" in blob
    titles = "\n".join(e["title"] for e in ex)
    assert "可组装切片" in titles
    assert "有脚手架挂路由" in titles
    assert "POST /api/v1/inspection/reports/{id}/approve" in blob
    assert "POST /api/v1/inspection/reports/{id}/dispatch" in blob
    assert "GET  /api/v1/inspection/reports" in blob or "GET /api/v1/inspection/reports" in blob
    assert "body: approved, comment" in blob
    assert "body: assignee_id" in blob
    assert "验收标准" in blob
    assert "npm run dev" in blob
    assert "无 project_scaffold" in blob
    assert "frontend/src/App.tsx" in blob
    assert "ReportFaultPage" in blob and "ApproveFaultPage" in blob and "DispatchRepairPage" in blob
    assert "TODO: auth" in blob
    assert "package.json" in blob
    assert "禁止交付 App.tsx" in blob


def test_backend_developer_examples_match_four_contracts():
    ex = build_agent_task_examples(
        display_name="后端开发工程师",
        description="根据 Architecture 中的 api_contracts 生成后端代码",
        skill_ids=["code_generation", "autoreview"],
    )
    blob = _assert_rich(ex)
    titles = "\n".join(e["title"] for e in ex)
    assert "单独测·可组装切片" in titles
    assert "POST /api/v1/inspection/reports/{id}/approve" in blob
    assert "POST /api/v1/inspection/reports/{id}/dispatch" in blob
    assert "GET  /api/v1/inspection/reports" in blob or "GET /api/v1/inspection/reports" in blob
    assert "无 project_scaffold" in blob
    assert "approved, comment" in blob
    assert "assignee_id" in blob


def test_programmer_agent_examples_share_isolated_coding_contract():
    ex = build_agent_task_examples(
        display_name="程序员",
        description="根据 PRD + 架构设计产出代码",
        skill_ids=["code_generation", "autoreview"],
    )
    blob = _assert_rich(ex)
    titles = "\n".join(e["title"] for e in ex)
    assert "单独测·可组装切片" in titles
    assert "approved, comment" in blob
    assert "禁止交付 App.tsx" in blob
    assert "Pydantic" in blob
    assert "无 project_scaffold" in blob
