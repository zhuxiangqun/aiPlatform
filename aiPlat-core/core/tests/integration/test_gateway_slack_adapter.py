import hashlib
import hmac
import importlib
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


class _Resp:
    def __init__(self, status: int = 200, text: str = "ok"):
        self.status = status
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Sess:
    def __init__(self, capture: dict):
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        self._capture["url"] = url
        self._capture["json"] = json
        return _Resp(200, "ok")


@pytest.mark.integration
def test_slack_command_posts_to_response_url(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    class DummyHarness:
        async def execute(self, req):
            return SimpleNamespace(ok=True, payload={"output": "hello"}, trace_id="t1", run_id="r1", error=None)

    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    capture = {}
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda *args, **kwargs: _Sess(capture))

    with TestClient(server.app) as client:
        body = "user_id=U1&text=hi&response_url=http%3A%2F%2Fexample.com%2Fresp&team_id=T1&channel_id=C1"
        r = client.post(
            "/api/core/gateway/slack/command",
            data=body,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200, r.text
        assert capture["url"] == "http://example.com/resp"
        assert capture["json"]["text"] == "hello"


@pytest.mark.integration
def test_slack_signature_verification_rejects_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_SLACK_SIGNING_SECRET", "secret")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app, raise_server_exceptions=False) as client:
        body = "user_id=U1&text=hi"
        ts = str(int(time.time()))
        # wrong signature
        r = client.post(
            "/api/core/gateway/slack/command",
            data=body,
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=deadbeef",
            },
        )
        assert r.status_code == 403


@pytest.mark.integration
def test_slack_signature_verification_accepts_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_SLACK_SIGNING_SECRET", "secret")

    import core.server as server

    importlib.reload(server)

    class DummyHarness:
        async def execute(self, req):
            return SimpleNamespace(ok=True, payload={"output": "ok"}, trace_id="t", run_id="r", error=None)

    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    with TestClient(server.app) as client:
        body = "user_id=U1&text=hi"
        ts = str(int(time.time()))
        base = f"v0:{ts}:{body}".encode("utf-8")
        sig = "v0=" + hmac.new(b"secret", base, hashlib.sha256).hexdigest()
        r = client.post(
            "/api/core/gateway/slack/command",
            data=body,
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert r.status_code == 200


@pytest.mark.integration
def test_slack_events_url_verification(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post("/api/core/gateway/slack/events", json={"type": "url_verification", "challenge": "abc"})
        assert r.status_code == 200
        assert r.json()["challenge"] == "abc"

