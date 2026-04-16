import time

from fastapi.testclient import TestClient


def test_execution_trace_link_api(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app
    from core.services import get_execution_store

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        store = get_execution_store()

        import anyio

        now = time.time()
        anyio.run(
            store.upsert_trace,
            {"trace_id": "t1", "name": "x", "status": "completed", "start_time": now, "end_time": now, "duration_ms": 1, "attributes": {}},
        )
        anyio.run(
            store.upsert_span,
            {"span_id": "s1", "trace_id": "t1", "name": "span", "status": "completed", "start_time": now, "end_time": now, "duration_ms": 1, "attributes": {}, "events": []},
        )
        anyio.run(
            store.upsert_agent_execution,
            {"id": "exec-a", "agent_id": "a1", "status": "completed", "input": {}, "output": {}, "start_time": now, "end_time": now, "duration_ms": 1, "trace_id": "t1"},
        )

        r = client.get("/api/core/executions/exec-a/trace")
        assert r.status_code == 200
        assert r.json()["trace_id"] == "t1"

        r = client.get("/api/core/traces/t1/executions")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items["agent_executions"]) == 1

