from fastapi.testclient import TestClient


def test_compiled_react_execute_and_resume_execute(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app

    with TestClient(app) as client:
        # force lifespan init
        client.get("/api/core/permissions/stats")

        r = client.post("/api/core/graphs/compiled/react/execute", json={"max_steps": 5, "checkpoint_interval": 1})
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        assert run_id

        r = client.get(f"/api/core/graphs/runs/{run_id}/checkpoints")
        assert r.status_code == 200
        checkpoints = r.json()["checkpoints"]
        assert len(checkpoints) >= 1
        checkpoint_id = checkpoints[0]["checkpoint_id"]

        r = client.post(f"/api/core/graphs/runs/{run_id}/resume/execute", json={"checkpoint_id": checkpoint_id, "max_steps": 5})
        assert r.status_code == 200
        payload = r.json()
        new_run_id = payload["run_id"]
        assert new_run_id and new_run_id != run_id

        r = client.get(f"/api/core/graphs/runs/{new_run_id}")
        assert r.status_code == 200
        run = r.json()
        assert run["parent_run_id"] == run_id
        assert run["resumed_from_checkpoint_id"] == checkpoint_id

