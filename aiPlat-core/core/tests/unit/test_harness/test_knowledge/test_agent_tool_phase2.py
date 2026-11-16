"""W6 Agent Tool：object.query / function.call 经 Facade；禁 SQL/直写。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.apps.tools.knowledge_agent_tools import FunctionCallTool, ObjectQueryTool


@pytest.mark.asyncio
async def test_object_query_rejects_sql():
    tool = ObjectQueryTool()
    out = await tool.execute(
        {
            "tenant_id": "t1",
            "object_type": "InstallOrder",
            "sql": "SELECT * FROM facts",
            "permissions": ["kb:read"],
        }
    )
    assert out.success is False
    assert "sql_or_write_forbidden" in (out.error or "")


@pytest.mark.asyncio
async def test_object_query_requires_tenant():
    tool = ObjectQueryTool()
    out = await tool.execute(
        {"object_type": "InstallOrder", "permissions": ["kb:read"]}
    )
    assert out.success is False
    assert out.error == "tenant_id_required"


@pytest.mark.asyncio
async def test_object_query_delegates_to_facade():
    tool = ObjectQueryTool()
    fake = {
        "status": "ok",
        "object_type": "InstallOrder",
        "total": 0,
        "items": [],
        "aggregates": [],
        "next_cursor": None,
    }
    with patch(
        "core.apps.tools.knowledge_agent_tools._facade_query_object_set",
        new_callable=AsyncMock,
        return_value=fake,
    ) as mock_q:
        out = await tool.execute(
            {
                "tenant_id": "t1",
                "object_type": "InstallOrder",
                "filter": {"status": "open"},
                "permissions": ["kb:read"],
            }
        )
    assert out.success is True
    mock_q.assert_awaited_once()
    args, kwargs = mock_q.await_args
    assert kwargs["tenant_id"] == "t1"
    assert kwargs["permissions"] == ["kb:read"]
    assert args[0]["object_type"] == "InstallOrder"


@pytest.mark.asyncio
async def test_object_query_policy_denied():
    tool = ObjectQueryTool()
    fake = {
        "status": "policy_denied",
        "reason": "missing_permissions:['kb:read']",
        "total": 0,
        "items": [],
    }
    with patch(
        "core.apps.tools.knowledge_agent_tools._facade_query_object_set",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        out = await tool.execute(
            {
                "tenant_id": "t1",
                "object_type": "InstallOrder",
                "permissions": ["kb:write"],
            }
        )
    assert out.success is False
    assert "missing_permissions" in (out.error or "")


@pytest.mark.asyncio
async def test_function_call_rejects_write_key():
    tool = FunctionCallTool()
    out = await tool.execute(
        {
            "function_id": "platform_function:knowledge:priority_hint",
            "params": {"write_fact": True},
            "permissions": ["kb:read"],
        }
    )
    assert out.success is False
    assert "sql_or_write_forbidden" in (out.error or "")


@pytest.mark.asyncio
async def test_function_call_ok():
    tool = FunctionCallTool()
    fake = {
        "status": "ok",
        "function_id": "platform_function:knowledge:priority_hint",
        "result": {"score": 40.0, "reason": "ok"},
    }
    with patch(
        "core.apps.tools.knowledge_agent_tools._facade_invoke_function",
        new_callable=AsyncMock,
        return_value=fake,
    ) as mock_i:
        out = await tool.execute(
            {
                "function_id": "platform_function:knowledge:priority_hint",
                "params": {"urgency": 2, "impact": 2},
                "permissions": ["kb:read"],
            }
        )
    assert out.success is True
    mock_i.assert_awaited_once()
    assert out.output["result"]["score"] == 40.0
