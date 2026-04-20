import time

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_change_control_returns_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.server import app
    from core.services import get_execution_store

    store = get_execution_store()
    now = time.time()
    anyio.run(
        store.add_syscall_event,
        {
            "id": "se-sum-1",
            "kind": "changeset",
            "name": "packages.install",
            "status": "approval_required",
            "target_type": "change",
            "target_id": "chg-sum-1",
            "approval_request_id": "apr-1",
            "created_at": now,
        },
    )

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.get("/api/core/change-control/changes/chg-sum-1")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["change_id"] == "chg-sum-1"
        assert isinstance(data.get("summary"), dict)
        assert data["summary"]["derived_state"] == "approval_required"

        r2 = client.get("/api/core/change-control/changes?limit=10&offset=0")
        assert r2.status_code == 200, r2.text
        data2 = r2.json()
        items = data2.get("items") or []
        assert any(isinstance(it.get("summary"), dict) for it in items)

