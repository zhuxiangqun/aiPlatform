import importlib
import time

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_audit_logs_support_time_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    now = time.time()

    with TestClient(server.app) as client:
        store = getattr(server, "_execution_store", None)
        assert store is not None

        async def _seed():
            await store.add_audit_log(action="x", status="ok", created_at=now - 120, detail={"n": 1})
            await store.add_audit_log(action="x", status="ok", created_at=now, detail={"n": 2})

        anyio.run(_seed)

        r = client.get("/api/core/audit/logs", params={"action": "x", "created_after": now - 10, "limit": 50, "offset": 0})
        assert r.status_code == 200, r.text
        items = r.json().get("items") or []
        assert len(items) == 1
        assert (items[0].get("detail") or {}).get("n") == 2

