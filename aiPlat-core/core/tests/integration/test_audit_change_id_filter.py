import time

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_audit_logs_filter_by_change_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.server import app
    from core.services import get_execution_store

    store = get_execution_store()
    import anyio

    async def _seed():
        await store.add_audit_log(
            action="gate_blocked",
            status="failed",
            tenant_id="t1",
            actor_id="admin",
            resource_type="change",
            resource_id="chg-111",
            change_id="chg-111",
            detail={"x": 1},
            created_at=time.time(),
        )

    anyio.run(_seed)

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.get("/api/core/audit/logs?change_id=chg-111&limit=10&offset=0")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] >= 1
        assert any(it.get("change_id") == "chg-111" for it in (data.get("items") or []))
