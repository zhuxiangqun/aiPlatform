"""UI-1 — package-plane jobs proxy (AIPLAT_EVAL_SERVICE_URL dual-mode)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request


@pytest.fixture(autouse=True)
def _clear_eval_url(monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_SERVICE_URL", raising=False)


@pytest.mark.asyncio
async def test_get_job_cohost_returns_execution_not_migrated():
    from apps.eval.api.jobs_api import get_eval_job

    req = MagicMock(spec=Request)
    req.method = "GET"
    req.headers = {}
    req.query_params = MagicMock()
    req.query_params.multi_items.return_value = []
    req.body = AsyncMock(return_value=b"")

    out = await get_eval_job(req, "job-x", _auth="t")
    assert out.status_code == 503
    body = out.body
    import json

    payload = json.loads(body)
    assert payload["error"]["code"] == "execution_not_migrated"
    assert payload["process_split_authorized"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_package_code_review_run_proxies_when_enabled(monkeypatch):
    from apps.eval.api.jobs_api import package_code_review_run

    monkeypatch.setenv("AIPLAT_EVAL_SERVICE_URL", "http://127.0.0.1:8010")

    req = MagicMock(spec=Request)
    req.method = "POST"
    req.headers = {"authorization": "Bearer t", "content-type": "application/json"}
    req.query_params = MagicMock()
    req.query_params.multi_items.return_value = []
    req.body = AsyncMock(return_value=b'{"gold":["a"],"findings":["a"]}')

    fake_resp = MagicMock()
    fake_resp.status_code = 202
    fake_resp.json.return_value = {
        "job_id": "j1",
        "status": "queued",
        "runner_id": "code_review_gold",
        "process_split_authorized": False,
    }
    fake_resp.content = b"{}"
    fake_resp.headers = {"content-type": "application/json"}

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=fake_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("apps.eval.api.eval_upstream.httpx.AsyncClient", return_value=mock_client):
        out = await package_code_review_run(req, _auth="t")

    assert out.status_code == 202
    args, _kwargs = mock_client.request.await_args
    assert args[0] == "POST"
    assert args[1] == "http://127.0.0.1:8010/api/platform/apps/eval/code-review-gold/run"


def test_probe_paths_include_jobs():
    from apps.eval.api.eval_upstream import _probe_paths

    paths = _probe_paths()
    assert "/jobs/{job_id}" in paths
    assert "/code-review-gold/run" in paths
