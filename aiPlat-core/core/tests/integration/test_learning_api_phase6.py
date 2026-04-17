import time

from fastapi.testclient import TestClient


def test_phase6_learning_artifacts_list_get_and_publish_rollback(tmp_path, monkeypatch):
    """
    Minimal management-plane API coverage:
    - list/get learning artifacts via HTTP
    - publish/rollback release_candidate transitions referenced artifacts
    """
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app
    from core.services import get_execution_store

    with TestClient(app) as client:
        store = get_execution_store()
        client.get("/api/core/permissions/stats")  # ensure lifespan init

        import anyio

        now = time.time()
        # Seed artifacts
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "pr-1",
                "kind": "prompt_revision",
                "target_type": "agent",
                "target_id": "a1",
                "version": "pr-1",
                "status": "draft",
                "payload": {"patch": {"prepend": "X"}},
                "metadata": {},
                "created_at": now,
            },
        )
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "rc-1",
                "kind": "release_candidate",
                "target_type": "agent",
                "target_id": "a1",
                "version": "rc-1",
                "status": "draft",
                "payload": {"artifact_ids": ["pr-1"], "summary": "x"},
                "metadata": {},
                "created_at": now,
            },
        )

    # List
        r = client.get("/api/core/learning/artifacts", params={"target_type": "agent", "target_id": "a1", "limit": 50, "offset": 0})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 2

    # Get
        r2 = client.get("/api/core/learning/artifacts/rc-1")
        assert r2.status_code == 200
        assert r2.json()["kind"] == "release_candidate"

    # Publish candidate (should publish referenced pr)
        r3 = client.post("/api/core/learning/releases/rc-1/publish", json={"user_id": "u1", "require_approval": False})
        assert r3.status_code == 200
        assert r3.json()["status"] == "published"

        rc = anyio.run(store.get_learning_artifact, "rc-1")
        pr = anyio.run(store.get_learning_artifact, "pr-1")
        assert rc["status"] == "published"
        assert pr["status"] == "published"

    # Rollback candidate (should rollback referenced pr)
        r4 = client.post("/api/core/learning/releases/rc-1/rollback", json={"user_id": "u1", "require_approval": False, "reason": "manual"})
        assert r4.status_code == 200
        assert r4.json()["status"] == "rolled_back"

        rc2 = anyio.run(store.get_learning_artifact, "rc-1")
        pr2 = anyio.run(store.get_learning_artifact, "pr-1")
        assert rc2["status"] == "rolled_back"
        assert pr2["status"] == "rolled_back"
