import importlib
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_onboarding_evidence_create_list_get(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        headers_admin = {"X-AIPLAT-TENANT-ID": "t1", "X-AIPLAT-ACTOR-ID": "admin1", "X-AIPLAT-ACTOR-ROLE": "admin"}

        c = client.post(
            "/api/core/onboarding/evidence/runs",
            json={
                "step_key": "adapter",
                "action": "configure_llm_adapter",
                "status": "ok",
                "input": {"name": "x"},
                "output": {"test": {"success": True}},
                "links": {"ui": "/onboarding"},
            },
            headers=headers_admin,
        )
        assert c.status_code == 200, c.text
        ev = c.json().get("evidence") or {}
        assert ev.get("id")
        # syscall event should be recorded for bidirectional linking
        db_path = tmp_path / "exec.sqlite3"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT COUNT(1) FROM syscall_events WHERE tenant_id=? AND target_type=? AND target_id=?",
                ("t1", "onboarding_evidence", str(ev.get("id"))),
            ).fetchone()
            assert int(row[0] or 0) >= 1
        finally:
            conn.close()

        lst = client.get("/api/core/onboarding/evidence/runs?step_key=adapter&limit=50&offset=0", headers=headers_admin)
        assert lst.status_code == 200, lst.text
        items = lst.json().get("items") or []
        assert any((it.get("id") == ev.get("id")) for it in items)

        g = client.get(f"/api/core/onboarding/evidence/runs/{ev.get('id')}", headers=headers_admin)
        assert g.status_code == 200, g.text
        assert g.json().get("id") == ev.get("id")
