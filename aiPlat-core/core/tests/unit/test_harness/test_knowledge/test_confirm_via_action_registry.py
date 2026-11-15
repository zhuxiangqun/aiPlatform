"""G2 收口：抽取 confirm 经 ActionRegistry L1（kb:write）。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all

ACTION_ID = "platform_action:knowledge:confirm_extraction"


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    return home


@pytest.mark.asyncio
async def test_confirm_action_l1_denied_without_kb_write(aiplat_home):
    """缺 kb:write → policy_denied。"""
    store = AsyncMock()
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    assert reg.get(ACTION_ID) is not None

    denied = await reg.execute(
        ACTION_ID,
        ("platform", "ext-denied"),
        {"extraction_id": "ext-denied"},
        actor="u1",
        permissions=["kb:read"],
        _bypass_approval=True,
    )
    assert denied.get("status") == "policy_denied", denied


@pytest.mark.asyncio
async def test_confirm_action_executes_with_kb_write(aiplat_home):
    """持有 kb:write 时走 handler 编排。"""
    store = AsyncMock()
    reg = AsyncActionRegistry(store=store)
    register_all(reg)

    fake = {
        "ok": True,
        "status": "confirmed",
        "path": "K1+graph+action",
        "extraction_id": "ext-ok",
        "signal_id": "sig-1",
        "yaml_unchanged": True,
        "wrote_live_yaml": False,
    }
    with patch(
        "core.api.core_facade.run_confirm_extraction",
        new=AsyncMock(return_value=fake),
    ):
        ok = await reg.execute(
            ACTION_ID,
            ("platform", "ext-ok"),
            {"extraction_id": "ext-ok"},
            actor="factory",
            permissions=["kb:write"],
            _bypass_approval=True,
        )
    assert ok.get("status") == "executed", ok
    body = ok.get("result") or {}
    assert body.get("status") == "confirmed"
    assert body.get("signal_id") == "sig-1"


@pytest.mark.asyncio
async def test_confirm_route_uses_action_registry():
    """HTTP confirm 委托 ActionRegistry，不再旁路 L1。"""
    from apps.fde.api import extraction_routes as routes

    mock_reg = MagicMock()
    mock_reg.execute = AsyncMock(
        return_value={
            "status": "executed",
            "result": {
                "ok": True,
                "status": "confirmed",
                "signal_id": "sig-x",
                "proposal_id": "prop-1",
                "wrote_live_yaml": False,
                "graph_write": {"created_entities": ["张三"]},
            },
        }
    )
    req = MagicMock()
    req.headers = {"X-AIPLAT-SCOPES": "kb:write"}

    with patch("core.api.core_facade.get_action_registry", return_value=mock_reg), patch(
        "apps.fde.api.extraction_routes.resolve_request_role", return_value="analyst"
    ):
        out = await routes.confirm_extraction(req, "ext-1", actor="factory")

    assert out["status"] == "confirmed"
    assert out["signal_id"] == "sig-x"
    assert out["proposal_id"] == "prop-1"
    mock_reg.execute.assert_awaited_once()
    kwargs = mock_reg.execute.await_args.kwargs
    assert kwargs.get("permissions") == ["kb:write"]
    assert mock_reg.execute.await_args.args[0] == ACTION_ID
