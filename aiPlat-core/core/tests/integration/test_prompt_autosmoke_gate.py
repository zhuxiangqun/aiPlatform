import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_prompt_upsert_returns_change_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.post(
            "/api/core/prompts",
            json={
                "template_id": "t1",
                "name": "t1",
                "template": "hello",
                "require_approval": False,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "updated"
        assert isinstance(data.get("change_id"), str) and data["change_id"].startswith("chg-")
        assert isinstance(data.get("links"), dict)


@pytest.mark.integration
def test_prompt_autosmoke_gate_blocks_upsert_when_verification_pending(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r1 = client.post(
            "/api/core/prompts",
            json={"template_id": "t2", "name": "t2", "template": "v1", "require_approval": False},
        )
        assert r1.status_code == 200, r1.text

        # Force verification.status=pending in DB to simulate autosmoke in-flight.
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT metadata_json FROM prompt_templates WHERE template_id=? LIMIT 1", ("t2",)).fetchone()
            md = json.loads(row[0] or "{}") if row and row[0] else {}
            md["verification"] = {"status": "pending", "updated_at": 1, "source": "test"}
            conn.execute("UPDATE prompt_templates SET metadata_json=? WHERE template_id=?", (json.dumps(md), "t2"))
            conn.commit()
        finally:
            conn.close()

        r2 = client.post(
            "/api/core/prompts",
            json={"template_id": "t2", "name": "t2", "template": "v2", "require_approval": False},
        )
        assert r2.status_code == 409, r2.text
        detail = (r2.json() or {}).get("detail") or {}
        assert detail.get("code") == "autosmoke_not_verified"
        assert isinstance(detail.get("change_id"), str) and detail["change_id"].startswith("chg-")
