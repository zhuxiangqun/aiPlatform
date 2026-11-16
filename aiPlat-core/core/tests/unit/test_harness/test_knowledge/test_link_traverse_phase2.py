"""W6 link.traverse：租户前置 + L1 + 多跳只读；禁 SQL/直写。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest

from core.apps.tools.knowledge_agent_tools import LinkTraverseTool
from core.harness.knowledge_pipeline.link_traverse import traverse_links


class _FakeLedger:
    """无 aiosqlite 依赖的事实注入（单测）。"""

    def __init__(self, facts: List[Dict[str, Any]]) -> None:
        self._facts = facts

    async def initialize(self) -> None:
        return None

    async def query_facts(
        self,
        *,
        tenant_id: str,
        domain_id: Optional[str] = None,
        limit: int = 2000,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        rows = [f for f in self._facts if f.get("tenant_id") == tenant_id]
        if domain_id:
            rows = [f for f in rows if f.get("domain_id") == domain_id]
        return rows[:limit]


def _fact(
    tenant_id: str,
    subject: str,
    predicate: str,
    obj: str,
    domain_id: str = "lock-service",
) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "domain_id": domain_id,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
    }


@pytest.fixture()
def ledger():
    return _FakeLedger(
        [
            _fact("t1", "InstallOrder:O-1", "status", "open"),
            _fact("t1", "InstallOrder:O-1", "assigned_to", "Person:P-1"),
            _fact("t1", "Person:P-1", "member_of", "Team:T-1"),
            _fact("t2", "InstallOrder:O-1", "assigned_to", "Person:P-SECRET"),
        ]
    )


@pytest.mark.asyncio
async def test_policy_denied_without_kb_read(ledger):
    out = await traverse_links(
        {"start_id": "InstallOrder:O-1"},
        tenant_id="t1",
        permissions=["kb:write"],
        ledger=ledger,
    )
    assert out["status"] == "policy_denied"
    assert "missing_permissions" in (out.get("reason") or "")


@pytest.mark.asyncio
async def test_tenant_isolation(ledger):
    out = await traverse_links(
        {"start_id": "InstallOrder:O-1", "max_hops": 2},
        tenant_id="t1",
        permissions=["kb:read"],
        ledger=ledger,
    )
    assert out["status"] == "ok"
    refs = {n["ref"] for n in out["nodes"]}
    assert "Person:P-1" in refs
    assert "Team:T-1" in refs
    assert "Person:P-SECRET" not in refs


@pytest.mark.asyncio
async def test_max_hops_one(ledger):
    out = await traverse_links(
        {"start_id": "InstallOrder:O-1", "max_hops": 1},
        tenant_id="t1",
        permissions=["kb:read"],
        ledger=ledger,
    )
    assert out["status"] == "ok"
    refs = {n["ref"] for n in out["nodes"]}
    assert "Person:P-1" in refs
    assert "Team:T-1" not in refs
    assert out["hops_reached"] == 1


@pytest.mark.asyncio
async def test_link_type_filter(ledger):
    out = await traverse_links(
        {
            "start_id": "InstallOrder:O-1",
            "link_types": ["assigned_to"],
            "max_hops": 2,
        },
        tenant_id="t1",
        permissions=["kb:read"],
        ledger=ledger,
    )
    assert out["status"] == "ok"
    refs = {n["ref"] for n in out["nodes"]}
    assert "Person:P-1" in refs
    assert "Team:T-1" not in refs


@pytest.mark.asyncio
async def test_tool_rejects_sql():
    tool = LinkTraverseTool()
    out = await tool.execute(
        {
            "tenant_id": "t1",
            "start_id": "InstallOrder:O-1",
            "sql": "SELECT 1",
            "permissions": ["kb:read"],
        }
    )
    assert out.success is False
    assert "sql_or_write_forbidden" in (out.error or "")


@pytest.mark.asyncio
async def test_tool_delegates_to_facade():
    tool = LinkTraverseTool()
    fake = {
        "status": "ok",
        "start_id": "InstallOrder:O-1",
        "nodes": [{"ref": "InstallOrder:O-1"}],
        "edges": [],
        "hops_reached": 0,
    }
    with patch(
        "core.apps.tools.knowledge_agent_tools._facade_traverse_links",
        new_callable=AsyncMock,
        return_value=fake,
    ) as mock_t:
        out = await tool.execute(
            {
                "tenant_id": "t1",
                "start_id": "InstallOrder:O-1",
                "permissions": ["kb:read"],
            }
        )
    assert out.success is True
    mock_t.assert_awaited_once()
    assert mock_t.await_args.kwargs["tenant_id"] == "t1"
