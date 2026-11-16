"""W6 object_set.aggregate Agent Tool：经 Facade；仅 count；禁 SQL/直写。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.apps.tools.knowledge_agent_tools import ObjectSetAggregateTool


@pytest.mark.asyncio
async def test_aggregate_rejects_sql():
    tool = ObjectSetAggregateTool()
    out = await tool.execute(
        {
            "tenant_id": "t1",
            "object_type": "InstallOrder",
            "aggregate": [{"type": "count"}],
            "sql": "SELECT COUNT(*)",
            "permissions": ["kb:read"],
        }
    )
    assert out.success is False
    assert "sql_or_write_forbidden" in (out.error or "")


@pytest.mark.asyncio
async def test_aggregate_requires_specs():
    tool = ObjectSetAggregateTool()
    out = await tool.execute(
        {
            "tenant_id": "t1",
            "object_type": "InstallOrder",
            "aggregate": [],
            "permissions": ["kb:read"],
        }
    )
    assert out.success is False
    assert out.error == "aggregate_required"


@pytest.mark.asyncio
async def test_aggregate_type_must_be_count():
    tool = ObjectSetAggregateTool()
    out = await tool.execute(
        {
            "tenant_id": "t1",
            "object_type": "InstallOrder",
            "aggregate": [{"type": "sum", "field": "amount"}],
            "permissions": ["kb:read"],
        }
    )
    assert out.success is False
    assert out.error == "aggregate_type_unsupported"


@pytest.mark.asyncio
async def test_aggregate_delegates_to_facade():
    tool = ObjectSetAggregateTool()
    fake = {
        "status": "ok",
        "object_type": "InstallOrder",
        "total": 2,
        "items": [],
        "aggregates": [{"status": "open", "count": 1}, {"status": "closed", "count": 1}],
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
                "aggregate": [{"type": "count", "group_by": ["status"]}],
                "permissions": ["kb:read"],
            }
        )
    assert out.success is True
    mock_q.assert_awaited_once()
    args, kwargs = mock_q.await_args
    assert kwargs["tenant_id"] == "t1"
    assert args[0]["aggregate"][0]["type"] == "count"
    assert out.output["aggregates"][0]["count"] == 1


@pytest.mark.asyncio
async def test_aggregate_policy_denied():
    tool = ObjectSetAggregateTool()
    fake = {
        "status": "policy_denied",
        "reason": "missing_permissions:['kb:read']",
        "aggregates": [],
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
                "aggregate": [{"type": "count"}],
                "permissions": ["kb:write"],
            }
        )
    assert out.success is False
    assert "missing_permissions" in (out.error or "")
