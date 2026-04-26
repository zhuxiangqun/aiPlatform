import time

from fastapi.testclient import TestClient


def test_canary_block_approval_marks_candidate_blocked_and_prevents_publish(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app
    from core.services import get_execution_store

    with TestClient(app) as client:
        store = get_execution_store()
        client.get("/api/core/permissions/stats")  # ensure lifespan init

        import anyio

        now = time.time()
        # Seed a release candidate
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "rc-1",
                "kind": "release_candidate",
                "target_type": "agent",
                "target_id": "a1",
                "version": "rc-1",
                "status": "draft",
                "payload": {"artifact_ids": [], "summary": "x"},
                "metadata": {},
                "created_at": now,
            },
        )

        # Seed a canary block approval request (created by canary_web in real flow)
        anyio.run(
            store.upsert_approval_request,
            {
                "request_id": "apr-1",
                "user_id": "system",
                "operation": "canary:block_release_candidate",
                "details": "canary block: P0",
                "rule_id": "canary_block",
                "rule_type": "sensitive_operation",
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "metadata": {"candidate_id": "rc-1", "project_id": "demo"},
                "result": {},
                "tenant_id": "demo",
                "actor_id": "system",
                "actor_role": "system",
                "session_id": "default",
                "run_id": "run-1",
            },
        )

        # Publishing should be blocked even while pending
        r0 = client.post("/api/core/learning/releases/rc-1/publish", json={"user_id": "u1", "require_approval": False})
        assert r0.status_code == 409

        # Approve the block -> should mark candidate metadata.blocked=true
        r1 = client.post("/api/core/approvals/apr-1/approve", json={"approved_by": "admin", "comments": "ack"})
        assert r1.status_code == 200

        # Wait for async callback to apply (best-effort)
        anyio.run(anyio.sleep, 0.05)

        rc = anyio.run(store.get_learning_artifact, "rc-1")
        assert rc["metadata"].get("blocked") is True
        assert rc["metadata"].get("blocked_via") == "canary"

        # Publishing should remain blocked after approval (approval means "approve blocking")
        r2 = client.post("/api/core/learning/releases/rc-1/publish", json={"user_id": "u1", "require_approval": False})
        assert r2.status_code == 409

