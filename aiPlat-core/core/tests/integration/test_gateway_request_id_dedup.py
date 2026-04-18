import importlib
import time

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_gateway_execute_dedup_by_request_id(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    run_id = "run_01J00000000000000000000000"
    req_id = "req_01J00000000000000000000000"
    now = time.time()

    with TestClient(server.app) as client:
        store = getattr(server, "_execution_store", None)
        assert store is not None

        async def _seed():
            await store.upsert_agent_execution(
                {
                    "id": run_id,
                    "agent_id": "agent_1",
                    "status": "running",
                    "input": {"messages": [{"role": "user", "content": "hi"}]},
                    "output": None,
                    "error": None,
                    "start_time": now,
                    "end_time": None,
                    "duration_ms": None,
                    "trace_id": "trace_1",
                    "metadata": {"user_id": "u1", "session_id": "s1"},
                    "approval_request_id": None,
                }
            )
            await store.remember_request_run_id(request_id=req_id, run_id=run_id, tenant_id=None)

        anyio.run(_seed)

        resp = client.post(
            "/api/core/gateway/execute",
            json={"channel": "webhook", "kind": "agent", "target_id": "agent_1", "payload": {"input": {"message": "hello"}}},
            headers={"X-AIPLAT-REQUEST-ID": req_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "deduped"
        assert body["run_id"] == run_id
        assert body["request_id"] == req_id

