"""Agent execution-examples LLM helpers (no live LLM required)."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from core.apps.agents.prompts import register_agents_prompts
from core.apps.agents.service.agent_execution_examples_llm import (
    generate_agent_execution_examples_llm,
)
from core.harness.utils.prompt_loader import _sync_resolve


def _fake_core_facade(llm_content: str = "not-json"):
    """Avoid importing real core_facade (KanbanEngine needs Python 3.10+)."""
    facade = MagicMock()
    facade._async_prompt_resolve = AsyncMock(side_effect=lambda pid, **kw: f"prompt:{pid}")
    facade.best_model_for_purpose = MagicMock(return_value="mock-model")
    facade.create_selected_adapter = MagicMock(return_value=MagicMock())
    facade.sys_llm_generate = AsyncMock(return_value=MagicMock(content=llm_content))
    return patch.dict(sys.modules, {"core.api.core_facade": facade}), facade


def test_agent_execution_examples_prompts_register():
    register_agents_prompts()
    sys_role = _sync_resolve("agent-execution-examples-system-role")
    body = _sync_resolve(
        "agent-execution-examples",
        agent_id="pm_agent",
        agent_name="产品经理",
        description="收集需求写 PRD",
        skills="requirement_analysis",
        tools="knowledge_retrieve",
        input_schema_json="{}",
        refine_hint="(无)",
        sop_excerpt="(无 SOP)",
    )
    assert "测试用例" in sys_role or "JSON" in sys_role
    assert "pm_agent" in body
    assert "产品经理" in body
    assert "code_generation" in body
    assert "先列文件清单再 file_operations" in body or "file_operations 落盘" in body
    assert "test_executor" in body
    assert "待执行的 test_cases" in body


def test_agent_execution_examples_llm_fallback_on_bad_json():
    async def _run():
        p, facade = _fake_core_facade("not-json")
        with p:
            result = await generate_agent_execution_examples_llm(
                agent_id="pm_agent",
                agent_name="产品经理",
                description="与用户对话收集需求，生成结构化PRD",
                skill_ids=["requirement_analysis"],
                tool_ids=[],
            )
        assert result["source"] == "heuristic_fallback"
        assert result["examples"]
        blob = "\n".join(e["content"] for e in result["examples"])
        assert "按本 Agent 的职责做一次冒烟验证" not in blob
        facade.best_model_for_purpose.assert_called_with("skill_execution")

    asyncio.run(_run())


def test_coding_llm_examples_need_fallback_detects_clarify_chips():
    from core.apps.agents.service.agent_execution_examples_llm import (
        _coding_llm_examples_need_fallback,
    )

    bad = [
        {
            "title": "最小可启动骨架生成",
            "content": (
                "请先列出你计划创建的文件清单，再执行 file_operations 落盘。"
                "若 PRD 未说明端口，请标注为待确认，不要自行假设后直接落盘。"
            ),
        },
        {"title": "澄清", "content": "第一步只输出澄清问题清单，覆盖技术栈版本。"},
    ]
    assert _coding_llm_examples_need_fallback(bad, ["code_generation", "file_operations"]) is True
    assert _coding_llm_examples_need_fallback(bad, ["requirement_analysis"]) is False
    good = [
        {
            "title": "可启动骨架",
            "content": "使用 ## FILE: 交付 main.py + Vite 入口。调用 code_generation → DONE。",
        }
    ]
    assert _coding_llm_examples_need_fallback(good, ["code_generation"]) is False
    todo = [
        {
            "title": "主路径：生成可启动前后端骨架",
            "content": (
                "待办事项 Web 应用，标记完成、删除。必须落盘。"
                "## FILE backend/main.py GET /api/todos。"
                "调用 code_generation，再用 file_operations 落盘，最后输出 DONE。"
            ),
        }
    ]
    assert (
        _coding_llm_examples_need_fallback(
            todo,
            ["code_generation"],
            agent_id="scaffold_agent",
            description="生成可启动的前后端工程骨架",
        )
        is True
    )


def test_executor_llm_examples_need_fallback_on_product_brief():
    from core.apps.agents.service.agent_execution_examples_llm import (
        _executor_llm_examples_need_fallback,
    )

    brief = [
        {
            "title": "复杂多约束",
            "content": (
                "【复杂冒烟｜测试执行器】角色/干系人：一线用户 + 审批/管理者。"
                "约束：钉钉 API 未开放与照片不上公网。明确 2 件本次不做。"
            ),
        },
        {"title": "简单", "content": "按本 Agent 职责完成一次最小可交付输出。"},
    ]
    assert _executor_llm_examples_need_fallback(
        brief, ["test_executor"], agent_id="test_executor"
    )
    good_exec = [
        {
            "title": "执行",
            "content": '{"message":"执行","test_cases":[{"id":"SMK-001","steps":["a"],"expected":"ok"}]}',
        },
        {"title": "空", "content": '{"test_cases":[]}'},
    ]
    assert not _executor_llm_examples_need_fallback(
        good_exec, ["test_executor"], agent_id="test_executor"
    )
    assert not _executor_llm_examples_need_fallback(brief, ["requirement_analysis"])


def test_coding_llm_clarify_chips_fall_back_to_heuristic():
    import json

    payload = json.dumps(
        [
            {
                "title": "最小可启动骨架生成",
                "content": (
                    "你是工程脚手架生成 Agent。请先列出你计划创建的文件清单，"
                    "再执行 file_operations 落盘。标注为待确认，不要自行假设后直接落盘。"
                    "验收：本机 npm install && npm run dev。"
                ),
            },
            {
                "title": "按 PRD 澄清后再生成",
                "content": "第一步只输出澄清问题清单，覆盖技术栈版本、是否需要鉴权。"
                "若用户未回答关键问题，请以待确认标注。",
            },
        ],
        ensure_ascii=False,
    )

    async def _run():
        p, facade = _fake_core_facade(payload)
        with p:
            result = await generate_agent_execution_examples_llm(
                agent_id="scaffold_agent",
                agent_name="工程脚手架生成",
                description="根据PRD和系统架构生成可启动的前后端工程骨架",
                skill_ids=["code_generation", "file_operations", "code-hygiene"],
                tool_ids=["file_operations"],
            )
        facade.best_model_for_purpose.assert_called_with("skill_execution")
        assert result["source"] == "heuristic_fallback"
        blob = "\n".join(e["content"] for e in result["examples"])
        assert "file_operations 落盘" not in blob
        assert "code_generation" in blob
        assert "可启动" in blob or "Vite" in blob or "FastAPI" in blob

    asyncio.run(_run())
