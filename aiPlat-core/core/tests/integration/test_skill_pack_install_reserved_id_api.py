import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_pack_install_skips_reserved_engine_skill_id(tmp_path, monkeypatch):
    """
    Workspace install should not be able to override engine skill ids.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Pick a reserved engine skill id (seeded by engine manager)
        r0 = client.get("/api/core/skills")
        assert r0.status_code == 200, r0.text
        skills = r0.json().get("skills") or []
        assert skills, "engine skills not seeded?"
        reserved_id = skills[0]["id"]

        r = client.post(
            "/api/core/skill-packs",
            json={
                "name": "pack-reserved",
                "manifest": {"skills": [{"id": reserved_id, "display_name": "Should Skip"}]},
            },
        )
        assert r.status_code == 200, r.text
        pack = r.json()

        r2 = client.post(f"/api/core/skill-packs/{pack['id']}/install", json={"scope": "workspace"})
        assert r2.status_code == 200, r2.text
        payload = r2.json()
        applied = payload.get("applied") or []
        rec = next((x for x in applied if x.get("skill_id") == reserved_id), None)
        assert rec is not None
        assert rec.get("status") == "skipped"
        assert "reserved" in (rec.get("reason") or "").lower()

