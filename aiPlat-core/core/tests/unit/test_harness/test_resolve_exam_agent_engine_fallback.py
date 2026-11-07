"""Exam agent resolve: workspace miss → engine AgentManager (eval_profile seeds)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_resolve_exam_agent_falls_back_to_engine_scope():
    from core.harness.evaluation.eval_runner import _resolve_exam_agent_info

    ctx = SimpleNamespace(workspace_id="default", kind="local", agents_dir="/tmp/ws")
    ws_mgr = MagicMock()
    ws_mgr.get_agent = AsyncMock(return_value=None)
    engine_agent = SimpleNamespace(
        id="conversational_agent",
        config={"eval_profile": {"capabilities": ["clarify_or_ask"]}},
        skills=[],
        tools=[],
        version="1.0.0",
        metadata={},
    )
    eng_mgr = MagicMock()
    eng_mgr.get_agent = AsyncMock(return_value=engine_agent)

    with (
        patch(
            "core.harness.named_workspace.resolve.get_active_named_workspace",
            return_value=ctx,
        ),
        patch(
            "core.harness.named_workspace.agent_mgr.agent_manager_for",
            return_value=ws_mgr,
        ),
        patch(
            "core.management.agent_manager.AgentManager",
            return_value=eng_mgr,
        ) as AM,
    ):
        got = await _resolve_exam_agent_info("conversational_agent")

    assert got is engine_agent
    AM.assert_called_once_with(seed=False, scope="engine")
    eng_mgr.get_agent.assert_awaited_once_with("conversational_agent")


@pytest.mark.asyncio
async def test_resolve_exam_agent_raises_when_neither_scope_has_agent():
    from core.harness.evaluation.eval_runner import _resolve_exam_agent_info

    ctx = SimpleNamespace(workspace_id="default", kind="local", agents_dir="/tmp/ws")
    ws_mgr = MagicMock()
    ws_mgr.get_agent = AsyncMock(return_value=None)
    eng_mgr = MagicMock()
    eng_mgr.get_agent = AsyncMock(return_value=None)

    with (
        patch(
            "core.harness.named_workspace.resolve.get_active_named_workspace",
            return_value=ctx,
        ),
        patch(
            "core.harness.named_workspace.agent_mgr.agent_manager_for",
            return_value=ws_mgr,
        ),
        patch(
            "core.management.agent_manager.AgentManager",
            return_value=eng_mgr,
        ),
        pytest.raises(FileNotFoundError, match="engine agents"),
    ):
        await _resolve_exam_agent_info("missing_agent")
