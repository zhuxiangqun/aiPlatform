"""A3-local — Central dual-mode proxy helper (AIPLAT_EVAL_SERVICE_URL)."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request


@pytest.fixture(autouse=True)
def _clear_eval_url(monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_SERVICE_URL", raising=False)


def test_proxy_disabled_by_default():
    from apps.eval.api.eval_upstream import eval_proxy_enabled, proxy_status

    assert eval_proxy_enabled() is False
    st = proxy_status()
    assert st["mode"] == "cohost"
    assert st["enabled"] is False
    assert st["process_split_authorized"] is False


def test_proxy_enabled_when_url_set(monkeypatch):
    from apps.eval.api.eval_upstream import eval_proxy_enabled, eval_service_base_url, proxy_status

    monkeypatch.setenv("AIPLAT_EVAL_SERVICE_URL", "http://127.0.0.1:8010/")
    assert eval_service_base_url() == "http://127.0.0.1:8010"
    assert eval_proxy_enabled() is True
    assert proxy_status()["mode"] == "proxy"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_proxy_eval_store_forwards(monkeypatch):
    from apps.eval.api.eval_upstream import proxy_eval_store

    monkeypatch.setenv("AIPLAT_EVAL_SERVICE_URL", "http://127.0.0.1:8010")

    req = MagicMock(spec=Request)
    req.method = "GET"
    req.headers = {"authorization": "Bearer t"}
    req.query_params = MagicMock()
    req.query_params.multi_items.return_value = [("limit", "10")]
    req.body = AsyncMock(return_value=b"")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"data": {"ok": True, "process_split_authorized": False}}
    fake_resp.content = b"{}"
    fake_resp.headers = {"content-type": "application/json"}

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=fake_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("apps.eval.api.eval_upstream.httpx.AsyncClient", return_value=mock_client):
        out = await proxy_eval_store(req, path="/store/healthz")

    assert out is not None
    assert out.status_code == 200
    mock_client.request.assert_awaited()
    args, kwargs = mock_client.request.await_args
    assert args[0] == "GET"
    assert args[1] == "http://127.0.0.1:8010/api/platform/apps/eval/store/healthz"


@pytest.mark.asyncio
async def test_proxy_returns_none_when_disabled():
    from apps.eval.api.eval_upstream import proxy_eval_store

    req = MagicMock(spec=Request)
    req.method = "GET"
    out = await proxy_eval_store(req, path="/store/sets")
    assert out is None
