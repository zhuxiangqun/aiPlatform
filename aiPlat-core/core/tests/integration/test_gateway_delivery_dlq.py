import importlib
import time

import pytest
from fastapi.testclient import TestClient


class _Resp:
    def __init__(self, status: int = 500, text: str = "fail"):
        self.status = status
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Sess:
    def __init__(self, status: int = 500):
        self._status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        return _Resp(self._status, "nope")


@pytest.mark.integration
def test_slack_response_delivery_failure_goes_to_dlq(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    # Make gateway_execute return a deterministic run_id
    class DummyHarness:
        async def execute(self, req):
            return type("R", (), {"ok": True, "payload": {"output": "hello"}, "trace_id": "t1", "run_id": "run_x", "error": None})()

    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    # Fail all webhook deliveries (slack response_url)
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda *args, **kwargs: _Sess(500))

    with TestClient(server.app) as client:
        body = "user_id=U1&text=hi&response_url=http%3A%2F%2Fexample.com%2Fresp&team_id=T1&channel_id=C1"
        r = client.post("/api/core/gateway/slack/command", data=body, headers={"content-type": "application/x-www-form-urlencoded"})
        assert r.status_code == 200, r.text

        # list DLQ (requires no admin token if not configured)
        dlq = client.get("/api/core/gateway/dlq", params={"status": "pending", "limit": 10})
        assert dlq.status_code == 200, dlq.text
        assert (dlq.json().get("total") or 0) == 1
        item = dlq.json()["items"][0]
        assert item["connector"] == "slack"
        assert item["url"] == "http://example.com/resp"

