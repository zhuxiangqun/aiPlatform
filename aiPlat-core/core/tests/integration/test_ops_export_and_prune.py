import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_ops_export_and_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        headers = {"X-AIPLAT-TENANT-ID": "t1", "X-AIPLAT-ACTOR-ID": "system", "X-AIPLAT-ACTOR-ROLE": "admin"}

        # ensure audit log exists
        client.put("/api/core/quota/snapshot", json={"tenant_id": "t1", "quota": {"daily": {"tool_calls": 1}}}, headers=headers)

        r = client.get("/api/core/ops/export/audit_logs.csv", params={"tenant_id": "t1", "limit": 50}, headers=headers)
        assert r.status_code == 200
        assert "text/csv" in (r.headers.get("content-type") or "")
        assert b"tenant_id" in r.content

        s = client.get("/api/core/ops/export/syscall_events.csv", params={"tenant_id": "t1", "limit": 50}, headers=headers)
        assert s.status_code == 200
        assert "text/csv" in (s.headers.get("content-type") or "")
        assert b"trace_id" in s.content

        # prune should succeed (best-effort)
        p = client.post("/api/core/ops/prune", json={"now_ts": 1e12}, headers=headers)
        assert p.status_code == 200
        assert p.json().get("ok") is True
