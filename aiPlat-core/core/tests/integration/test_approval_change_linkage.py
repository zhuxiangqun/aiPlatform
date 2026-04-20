import time

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_pending_approvals_include_change_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.server import app
    from core.services import get_execution_store

    store = get_execution_store()
    now = time.time()

    async def _seed():
        await store.upsert_approval_request(
            {
                "request_id": "apr-1",
                "user_id": "admin",
                "operation": "learning:release.rollback",
                "details": "x",
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "metadata": {"candidate_id": "cand-1"},
            }
        )
        await store.add_syscall_event(
            {
                "id": "se-apr-1",
                "kind": "changeset",
                "name": "learning.rollback",
                "status": "approval_required",
                "target_type": "change",
                "target_id": "chg-apr-1",
                "approval_request_id": "apr-1",
                "created_at": now,
            }
        )

    anyio.run(_seed)

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.get("/api/core/approvals/pending?limit=50&offset=0")
        assert r.status_code == 200, r.text
        data = r.json()
        item = (data.get("items") or [None])[0]
        assert item["request_id"] == "apr-1"
        assert item.get("change_id") == "chg-apr-1"
        assert isinstance(item.get("change_links"), dict)

