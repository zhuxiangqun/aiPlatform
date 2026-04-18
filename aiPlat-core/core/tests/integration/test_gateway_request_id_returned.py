import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_gateway_execute_returns_request_id_and_persists_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    req_id = "req_01J00000000000000000000000"

    with TestClient(server.app) as client:
        # Use a pure tool execution to avoid LLM dependencies.
        resp = client.post(
            "/api/core/gateway/execute",
            json={
                "channel": "webhook",
                "kind": "tool",
                "target_id": "calculator",
                "payload": {"expression": "1+1"},
            },
            headers={"X-AIPLAT-REQUEST-ID": req_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("request_id") == req_id
        assert isinstance(body.get("run_id"), str) and body["run_id"].startswith("run_")

        store = getattr(server, "_execution_store", None)
        assert store is not None
        # Ensure mapping is persisted.
        got = anyio.run(lambda: store.get_run_id_for_request(request_id=req_id, tenant_id=None))
        assert got == body["run_id"]
