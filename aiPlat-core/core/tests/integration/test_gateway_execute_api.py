import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_gateway_execute_injects_channel_context(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    captured = {}

    class DummyHarness:
        async def execute(self, req):
            captured["req"] = req
            # Echo the request payload back so we can assert context injection.
            return SimpleNamespace(
                ok=True,
                payload={"echo": req.payload},
                trace_id="trace-test",
                run_id="run-test",
                error=None,
            )

    # Patch gateway to use dummy harness
    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/gateway/execute",
            json={
                "channel": "slack",
                "kind": "agent",
                "target_id": "agent_1",
                "user_id": "u1",
                "session_id": "s1",
                "payload": {"input": {"text": "hi"}, "context": {"foo": "bar"}},
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["trace_id"] == "trace-test"
        assert data["run_id"] == "run-test"

        echoed = data["echo"]
        assert echoed["context"]["foo"] == "bar"
        assert echoed["context"]["source"] == "gateway"
        assert echoed["context"]["channel"] == "slack"


@pytest.mark.integration
def test_gateway_execute_reports_error_on_ok_false(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    class DummyHarness:
        async def execute(self, req):
            return SimpleNamespace(
                ok=False,
                payload={"details": "bad input"},
                trace_id="trace-bad",
                run_id="run-bad",
                error="bad input",
            )

    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/gateway/execute",
            json={
                "channel": "web",
                "kind": "skill",
                "target_id": "skill_1",
                "user_id": "u1",
                "session_id": "s1",
                "payload": {"input": {"x": 1}, "context": {}},
            },
        )
        # API currently returns 200 with ok=false payload
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is False
        assert data["trace_id"] == "trace-bad"
        assert data["run_id"] == "run-bad"
        assert data.get("error")
        # Backward compatible: may include error_detail
        assert "error_detail" in data


@pytest.mark.integration
def test_gateway_execute_returns_500_on_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    class DummyHarness:
        async def execute(self, req):
            raise RuntimeError("boom")

    monkeypatch.setattr(server, "get_harness", lambda: DummyHarness(), raising=True)

    # In TestClient, server exceptions are re-raised by default; disable to assert 500.
    with TestClient(server.app, raise_server_exceptions=False) as client:
        r = client.post(
            "/api/core/gateway/execute",
            json={
                "channel": "web",
                "kind": "skill",
                "target_id": "skill_1",
                "user_id": "u1",
                "session_id": "s1",
                "payload": {"input": {"x": 1}, "context": {}},
            },
        )
        assert r.status_code == 500, r.text
