"""Agent execution-examples LLM helpers (no live LLM required)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.apps.agents.prompts import register_agents_prompts
from core.apps.agents.service.agent_execution_examples_llm import (
    generate_agent_execution_examples_llm,
)
from core.harness.utils.prompt_loader import _sync_resolve


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
    )
    assert "测试用例" in sys_role or "JSON" in sys_role
    assert "pm_agent" in body
    assert "产品经理" in body


def test_agent_execution_examples_llm_fallback_on_bad_json():
    async def _run():
        with (
            patch(
                "core.api.core_facade._async_prompt_resolve",
                new=AsyncMock(side_effect=lambda pid, **kw: f"prompt:{pid}"),
            ),
            patch("core.api.core_facade.best_model_for_purpose", return_value="mock-model"),
            patch("core.api.core_facade.create_selected_adapter", return_value=MagicMock()),
            patch(
                "core.api.core_facade.sys_llm_generate",
                new=AsyncMock(return_value=MagicMock(content="not-json")),
            ),
        ):
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

    asyncio.run(_run())
