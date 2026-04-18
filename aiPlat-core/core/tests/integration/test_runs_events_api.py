import importlib
import time

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_runs_and_events_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    run_id = "run_01J00000000000000000000000"
    now = time.time()

    with TestClient(server.app) as client:
        store = getattr(server, "_execution_store", None)
        assert store is not None

        async def _seed():
            await store.upsert_agent_execution(
                {
                    "id": run_id,
                    "agent_id": "agent_1",
                    "status": "completed",
                    "input": {"messages": [{"role": "user", "content": "hi"}]},
                    "output": "ok",
                    "error": None,
                    "start_time": now,
                    "end_time": now + 1,
                    "duration_ms": 1000,
                    "trace_id": "trace_1",
                    "metadata": {},
                    "approval_request_id": None,
                }
            )
            await store.append_run_event(run_id=run_id, event_type="run_start", trace_id="trace_1", payload={"kind": "agent"})
            await store.append_run_event(run_id=run_id, event_type="run_end", trace_id="trace_1", payload={"kind": "agent", "status": "completed"})

        anyio.run(_seed)

        r = client.get(f"/api/core/runs/{run_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["run_id"] == run_id
        assert data["target_type"] == "agent"

        e = client.get(f"/api/core/runs/{run_id}/events", params={"after_seq": 0, "limit": 50})
        assert e.status_code == 200, e.text
        events = e.json()["items"]
        assert len(events) >= 2
        assert events[0]["type"] == "run_start"
        assert events[-1]["type"] == "run_end"

        w = client.post(f"/api/core/runs/{run_id}/wait", json={"timeout_ms": 1000, "after_seq": 0})
        assert w.status_code == 200, w.text
        wd = w.json()
        assert wd["done"] is True
