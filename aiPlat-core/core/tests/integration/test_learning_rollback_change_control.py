import time

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_learning_rollback_approval_required_returns_change_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    # ensure autosmoke gate doesn't interfere in this test
    monkeypatch.setenv("AIPLAT_AUTOSMOKE_ENFORCE", "false")

    from core.server import app
    from core.services import get_execution_store

    store = get_execution_store()
    now = time.time()

    import anyio

    anyio.run(
        store.upsert_learning_artifact,
        {
            "artifact_id": "rc-cc-1",
            "kind": "release_candidate",
            "target_type": "agent",
            "target_id": "a1",
            "version": "rc",
            "status": "published",
            "payload": {"artifact_ids": []},
            "metadata": {},
            "created_at": now,
        },
    )

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")  # ensure lifespan init
        r = client.post("/api/core/learning/releases/rc-cc-1/rollback", json={"user_id": "u1", "require_approval": True})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "approval_required"
        assert str(data.get("change_id") or "").startswith("chg-")

