"""W6 action.execute Agent Tool：经 Facade；禁 SQL/直写；禁 bypass。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.apps.tools.knowledge_agent_tools import ActionExecuteTool


@pytest.mark.asyncio
async def test_execute_rejects_sql():
    tool = ActionExecuteTool()
    out = await tool.execute(
        {
            "action_id": "platform_action:knowledge:confirm_extraction",
            "entity_id": "ext-1",
            "sql": "UPDATE facts",
            "permissions": ["kb:write"],
        }
    )
    assert out.success is False
    assert "sql_or_write_forbidden" in (out.error or "")


@pytest.mark.asyncio
async def test_execute_rejects_bypass_approval():
    tool = ActionExecuteTool()
    out = await tool.execute(
        {
            "action_id": "platform_action:knowledge:confirm_extraction",
            "entity_id": "ext-1",
            "_bypass_approval": True,
            "permissions": ["kb:write"],
        }
    )
    assert out.success is False
    assert out.error == "bypass_approval_forbidden"


@pytest.mark.asyncio
async def test_execute_requires_action_and_entity():
    tool = ActionExecuteTool()
    missing_action = await tool.execute({"entity_id": "e1"})
    assert missing_action.success is False
    assert missing_action.error == "action_id_required"

    missing_entity = await tool.execute(
        {"action_id": "platform_action:knowledge:confirm_extraction"}
    )
    assert missing_entity.success is False
    assert missing_entity.error == "entity_ref_required"


@pytest.mark.asyncio
async def test_execute_delegates_to_facade():
    tool = ActionExecuteTool()
    fake = {
        "status": "executed",
        "action_id": "platform_action:knowledge:confirm_extraction",
        "result": {"ok": True},
    }
    with patch(
        "core.apps.tools.knowledge_agent_tools._facade_execute_action",
        new_callable=AsyncMock,
        return_value=fake,
    ) as mock_e:
        out = await tool.execute(
            {
                "action_id": "platform_action:knowledge:confirm_extraction",
                "domain_id": "platform",
                "entity_id": "ext-ok",
                "params": {"extraction_id": "ext-ok"},
                "permissions": ["kb:write"],
                "actor": "agent-1",
            }
        )
    assert out.success is True
    mock_e.assert_awaited_once()
    args, kwargs = mock_e.await_args
    assert args[0] == "platform_action:knowledge:confirm_extraction"
    assert args[1] == ("platform", "ext-ok")
    assert args[2]["extraction_id"] == "ext-ok"
    assert kwargs["permissions"] == ["kb:write"]
    assert kwargs["actor"] == "agent-1"


@pytest.mark.asyncio
async def test_execute_policy_denied():
    tool = ActionExecuteTool()
    fake = {
        "status": "policy_denied",
        "reason": "missing_permissions:['kb:write']",
    }
    with patch(
        "core.apps.tools.knowledge_agent_tools._facade_execute_action",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        out = await tool.execute(
            {
                "action_id": "platform_action:knowledge:confirm_extraction",
                "entity_id": "ext-1",
                "permissions": ["kb:read"],
            }
        )
    assert out.success is False
    assert "missing_permissions" in (out.error or "")
