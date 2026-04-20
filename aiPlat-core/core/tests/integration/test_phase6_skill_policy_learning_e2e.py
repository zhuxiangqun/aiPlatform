import time

import anyio
from fastapi.testclient import TestClient


def test_phase6_skill_release_publish_materializes_workspace_version(tmp_path, monkeypatch):
    """
    E2E-ish check for Skill self-evolution publish:
    - create a workspace skill
    - seed a skill_evolution artifact + release_candidate
    - publish candidate
    - assert candidate metadata contains rollback pointer and workspace skill version is bumped
    """
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("HOME", str(tmp_path))  # isolate workspace dirs under tmp

    from core.server import app
    from core.services import get_execution_store

    with TestClient(app) as client:
        store = get_execution_store()
        client.get("/api/core/permissions/stats")  # ensure lifespan init

        # Create a workspace skill via HTTP (so workspace manager is ready)
        r = client.post(
            "/api/core/workspace/skills",
            json={
                "name": "Skill A",
                "category": "general",
                "description": "desc",
                "template": "",
                "sop": "do X",
                "config": {},
                "input_schema": {},
                "output_schema": {},
            },
        )
        assert r.status_code == 200
        sid = r.json().get("skill_id") or r.json().get("id") or r.json().get("skill", {}).get("id")
        assert sid

        now = time.time()
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "se-1",
                "kind": "skill_evolution",
                "target_type": "skill",
                "target_id": str(sid),
                "version": "se-1",
                "status": "draft",
                "payload": {"suggestion": "add guardrails"},
                "metadata": {},
                "created_at": now,
            },
        )
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "rc-skill-1",
                "kind": "release_candidate",
                "target_type": "skill",
                "target_id": str(sid),
                "version": "rc-skill-1",
                "status": "draft",
                "payload": {"artifact_ids": ["se-1"], "summary": "skill evolve"},
                "metadata": {},
                "created_at": now,
            },
        )

        # Publish (approval bypass for this test)
        r2 = client.post("/api/core/learning/releases/rc-skill-1/publish", json={"user_id": "u1", "require_approval": False})
        assert r2.status_code == 200
        assert r2.json()["status"] in ("published", "approval_required")
        assert r2.json()["status"] == "published"

        cand = anyio.run(store.get_learning_artifact, "rc-skill-1")
        assert cand["status"] == "published"
        meta = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else {}
        assert meta.get("published_workspace_skill_id") == str(sid)
        assert meta.get("rollback_to_skill_version") is not None


def test_phase6_policy_revision_publish_and_rollback(tmp_path, monkeypatch):
    """
    Policy self-evolution:
    - seed current tenant policy
    - seed policy_revision + release_candidate
    - publish requires approval (forced); simulate approved request
    - verify policy updated
    - rollback reverts to previous snapshot
    """
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app
    from core.services import get_execution_store

    with TestClient(app) as client:
        store = get_execution_store()
        client.get("/api/core/permissions/stats")  # ensure lifespan init

        # Seed baseline policy
        r0 = client.put("/api/core/policy/snapshot", json={"tenant_id": "t1", "policy": {"tools": {"allow": ["read"]}}})
        assert r0.status_code == 200

        now = time.time()
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "pol-1",
                "kind": "policy_revision",
                "target_type": "policy",
                "target_id": "t1",
                "version": "pol-1",
                "status": "draft",
                "payload": {"patch": {"tools": {"allow": ["read", "write"]}}},
                "metadata": {},
                "created_at": now,
            },
        )
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "rc-pol-1",
                "kind": "release_candidate",
                "target_type": "policy",
                "target_id": "t1",
                "version": "rc-pol-1",
                "status": "draft",
                "payload": {"artifact_ids": ["pol-1"], "summary": "policy evolve"},
                "metadata": {},
                "created_at": now,
            },
        )

        # Simulate an approved approval_request
        anyio.run(
            store.upsert_approval_request,
            {
                "request_id": "apr-1",
                "user_id": "admin",
                "operation": "learning:publish_release",
                "details": "approve policy publish",
                "rule_id": "test",
                "rule_type": "sensitive_operation",
                "status": "approved",
                "amount": None,
                "batch_size": None,
                "is_first_time": False,
                "created_at": now,
                "updated_at": now,
                "expires_at": None,
                "metadata": {},
                "result": {"approved": True},
                "tenant_id": "",
                "actor_id": "admin",
                "actor_role": "admin",
                "session_id": "s1",
                "run_id": None,
            },
        )

        r1 = client.post(
            "/api/core/learning/releases/rc-pol-1/publish",
            json={"user_id": "admin", "require_approval": True, "approval_request_id": "apr-1"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "published"

        # policy should be updated
        p1 = client.get("/api/core/policy/snapshot", params={"tenant_id": "t1"})
        assert p1.status_code == 200
        assert p1.json()["policy"]["tools"]["allow"] == ["read", "write"]

        # rollback should revert
        r2 = client.post("/api/core/learning/releases/rc-pol-1/rollback", json={"user_id": "admin", "require_approval": False, "reason": "test"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "rolled_back"

        p2 = client.get("/api/core/policy/snapshot", params={"tenant_id": "t1"})
        assert p2.status_code == 200
        assert p2.json()["policy"]["tools"]["allow"] == ["read"]

