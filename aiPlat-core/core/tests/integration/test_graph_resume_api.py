import time

from fastapi.testclient import TestClient


def test_graph_resume_api_creates_new_run(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app
    from core.services import get_execution_store

    with TestClient(app) as client:
        # force lifespan init
        client.get("/api/core/permissions/stats")
        store = get_execution_store()

        import anyio

        parent_run_id = anyio.run(store.start_graph_run, "g1", None, {"step_count": 0, "metadata": {"graph_run_id": "parent"}})
        ckpt_id = anyio.run(
            store.add_graph_checkpoint,
            parent_run_id,
            1,
            {"step_count": 1, "current_node": "b", "metadata": {"graph_run_id": parent_run_id}},
            None,
            time.time(),
        )

        r = client.post(f"/api/core/graphs/runs/{parent_run_id}/resume", json={"checkpoint_id": ckpt_id})
        assert r.status_code == 200
        payload = r.json()
        assert payload["checkpoint_id"] == ckpt_id
        new_run_id = payload["run_id"]

        r = client.get(f"/api/core/graphs/runs/{new_run_id}")
        assert r.status_code == 200
        run = r.json()
        assert run["parent_run_id"] == parent_run_id
        assert run["resumed_from_checkpoint_id"] == ckpt_id

