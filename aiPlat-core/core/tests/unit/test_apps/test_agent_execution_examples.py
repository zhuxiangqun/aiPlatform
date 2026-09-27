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
