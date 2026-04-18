import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_gateway_pairing_resolves_user_and_session(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    captured = {}

    class DummyHarness:
        async def execute(self, req):
            captured["req"] = req
            return SimpleNamespace(ok=True, payload={"ok": True}, trace_id="t", run_id="r", error=None)

    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    with TestClient(server.app) as client:
        # Create pairing
        r0 = client.post(
            "/api/core/gateway/pairings",
            json={"channel": "slack", "channel_user_id": "U123", "user_id": "u1", "session_id": "s1"},
        )
        assert r0.status_code == 200, r0.text

        r = client.post(
            "/api/core/gateway/execute",
            json={
                "channel": "slack",
                "kind": "agent",
                "target_id": "agent_1",
                "channel_user_id": "U123",
                "payload": {"input": {"text": "hi"}, "context": {}},
            },
        )
        assert r.status_code == 200, r.text
        assert captured["req"].user_id == "u1"
        assert captured["req"].session_id == "s1"


@pytest.mark.integration
def test_gateway_auth_token_required_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_GATEWAY_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_GATEWAY_TOKEN", "secret-token")

    import core.server as server

    importlib.reload(server)

    class DummyHarness:
        async def execute(self, req):
            return SimpleNamespace(ok=True, payload={"ok": True}, trace_id="t", run_id="r", error=None)

    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    with TestClient(server.app, raise_server_exceptions=False) as client:
        r1 = client.post(
            "/api/core/gateway/execute",
            json={"channel": "web", "kind": "agent", "target_id": "a1", "payload": {"input": {"x": 1}}},
        )
        assert r1.status_code == 401

        r2 = client.post(
            "/api/core/gateway/execute",
            headers={"X-AiPlat-Gateway-Token": "secret-token"},
            json={"channel": "web", "kind": "agent", "target_id": "a1", "payload": {"input": {"x": 1}}},
        )
        assert r2.status_code == 200, r2.text


@pytest.mark.integration
def test_gateway_webhook_message_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    captured = {}

    class DummyHarness:
        async def execute(self, req):
            captured["req"] = req
            return SimpleNamespace(ok=True, payload={"ok": True}, trace_id="t", run_id="r", error=None)

    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    with TestClient(server.app) as client:
        client.post(
            "/api/core/gateway/pairings",
            json={"channel": "slack", "channel_user_id": "U999", "user_id": "u9", "session_id": "s9"},
        )
        r = client.post(
            "/api/core/gateway/webhook/message",
            json={"channel": "slack", "channel_user_id": "U999", "kind": "agent", "target_id": "a1", "text": "hi"},
        )
        assert r.status_code == 200, r.text
        assert captured["req"].user_id == "u9"
        assert captured["req"].session_id == "s9"
        assert captured["req"].payload["input"]["message"] == "hi"
