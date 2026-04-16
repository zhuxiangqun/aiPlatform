import time

from fastapi.testclient import TestClient


def test_trace_api_roundtrip(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app
    from core.services import get_execution_store

    with TestClient(app) as client:
        store = get_execution_store()

        # create trace + span directly via store
        now = time.time()
        client.get("/api/core/permissions/stats")  # ensure lifespan init

        import anyio

        anyio.run(
            store.upsert_trace,
            {
                "trace_id": "t1",
                "name": "trace",
                "status": "completed",
                "start_time": now,
                "end_time": now,
                "duration_ms": 1,
                "attributes": {"k": "v"},
            },
        )
        anyio.run(
            store.upsert_span,
            {
                "span_id": "s1",
                "trace_id": "t1",
                "parent_span_id": None,
                "name": "span",
                "status": "completed",
                "start_time": now,
                "end_time": now,
                "duration_ms": 1,
                "attributes": {"a": 1},
                "events": [],
            },
        )

        r = client.get("/api/core/traces")
        assert r.status_code == 200
        payload = r.json()
        assert payload["total"] >= 1

        r = client.get("/api/core/traces/t1")
        assert r.status_code == 200
        t = r.json()
        assert t["trace_id"] == "t1"
        assert len(t.get("spans", [])) == 1

