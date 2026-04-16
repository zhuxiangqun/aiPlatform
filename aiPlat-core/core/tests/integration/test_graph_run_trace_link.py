from fastapi.testclient import TestClient


def test_graph_run_persists_trace_id(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app

    with TestClient(app) as client:
        # init
        client.get("/api/core/permissions/stats")

        r = client.post("/api/core/graphs/compiled/react/execute", json={"messages": [], "context": {}, "max_steps": 1})
        assert r.status_code == 200
        run_id = r.json()["run_id"]

        run = client.get(f"/api/core/graphs/runs/{run_id}").json()
        assert run.get("trace_id") is not None

        trace_id = run["trace_id"]
        # list filter by trace_id should include the run
        runs = client.get(f"/api/core/graphs/runs?trace_id={trace_id}&limit=10&offset=0").json()
        assert any(x["run_id"] == run_id for x in runs.get("runs", []))

