import time

from fastapi.testclient import TestClient


def test_list_graph_runs_api(tmp_path, monkeypatch):
    db_path = tmp_path / "runs.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app
    from core.services import get_execution_store

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        store = get_execution_store()

        import anyio

        now = time.time()
        anyio.run(store.start_graph_run, "react", "r1", {"a": 1}, now)
        anyio.run(store.finish_graph_run, "r1", "completed", None, None, now + 1)

        r = client.get("/api/core/graphs/runs?limit=10&offset=0")
        assert r.status_code == 200
        payload = r.json()
        assert payload["total"] >= 1
        assert any(x["run_id"] == "r1" for x in payload["runs"])
