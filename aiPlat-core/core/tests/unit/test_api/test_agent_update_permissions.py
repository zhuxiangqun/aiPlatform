"""Agent update must persist top-level permissions into AGENT.md metadata."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.schemas_agents import AgentUpdateRequest


@pytest.mark.asyncio
async def test_update_merges_top_level_permissions_into_metadata(monkeypatch):
    calls = []

    async def _fake_update(agent_id, **kwargs):
        calls.append({"agent_id": agent_id, "kwargs": dict(kwargs)})
        return SimpleNamespace(id=agent_id, name="pm", metadata=(kwargs.get("metadata") or {}))

    mgr = SimpleNamespace(
        update_agent=AsyncMock(side_effect=_fake_update),
        get_agent=AsyncMock(return_value=None),
    )

    from core.api.routers import workspace_agents as wa

    monkeypatch.setattr(wa, "_ws_agent_mgr", lambda rt=None: mgr)
    monkeypatch.setattr(wa, "_store", lambda rt=None: None)
    monkeypatch.setattr(wa, "_job_scheduler", lambda rt=None: None)

    req = AgentUpdateRequest(
        metadata={"loop_type": "react"},
        permissions=["llm:generate", "fs:read"],
        trigger_conditions=["需求分析"],
    )
    http_request = SimpleNamespace(headers={})

    resp = await wa.update_workspace_agent("pm_agent", req, http_request, rt=None)
    assert resp["id"] == "pm_agent"
    assert resp["status"] == "updated"
    assert calls, "update_agent should be called"
    meta = calls[0]["kwargs"]["metadata"]
    assert meta["loop_type"] == "react"
    assert meta["permissions"] == ["llm:generate", "fs:read"]
    assert meta["trigger_conditions"] == ["需求分析"]
