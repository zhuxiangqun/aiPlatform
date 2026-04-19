import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_session_lock_causes_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_SESSION_QUEUE_ENABLED", "true")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        store = getattr(server, "_execution_store", None)
        assert store is not None

        # Hold lock for (tenant, session) to force queueing
        anyio.run(
            lambda: store.try_acquire_session_lock(tenant_id="t_demo", session_id="s_demo", run_id="run_active", ttl_seconds=300)
        )

        r = client.post(
            "/api/core/tools/calculator/execute",
            json={"expression": "1+2", "user_id": "u1", "session_id": "s_demo"},
            headers={"X-AIPLAT-TENANT-ID": "t_demo"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") in {"accepted", "running"}  # v2 normalized
        assert body.get("legacy_status") == "queued"
        run_id = body.get("run_id")
        assert isinstance(run_id, str) and run_id

        ev = client.get(f"/api/core/runs/{run_id}/events", params={"after_seq": 0, "limit": 50})
        assert ev.status_code == 200, ev.text
        types = [x.get("type") for x in (ev.json().get("items") or [])]
        assert "queued" in types

