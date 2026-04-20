import time

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_change_control_evidence_export_json(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.server import app
    from core.services import get_execution_store

    store = get_execution_store()
    now = time.time()
    anyio.run(
        store.add_syscall_event,
        {
            "id": "se-ev-1",
            "kind": "changeset",
            "name": "packages.install",
            "status": "success",
            "target_type": "change",
            "target_id": "chg-ev-1",
            "created_at": now,
        },
    )
    async def _seed():
        await store.add_audit_log(
            action="autosmoke_enqueued",
            status="ok",
            tenant_id="t1",
            actor_id="admin",
            resource_type="change",
            resource_id="chg-ev-1",
            change_id="chg-ev-1",
            detail={"x": 1},
            created_at=now,
        )

    anyio.run(_seed)

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.get("/api/core/change-control/changes/chg-ev-1/evidence?format=json&limit=50")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["change_id"] == "chg-ev-1"
        assert "change_control" in data
        assert "audit" in data
