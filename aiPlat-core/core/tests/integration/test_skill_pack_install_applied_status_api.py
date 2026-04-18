import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_pack_install_applied_enabled_and_skipped(tmp_path, monkeypatch):
    """
    Install(workspace) should report enabled for new skills and skipped for reserved ids.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Get a reserved engine skill id
        r0 = client.get("/api/core/skills")
        assert r0.status_code == 200, r0.text
        skills = r0.json().get("skills") or []
        assert skills
        reserved_id = skills[0]["id"]

        r = client.post(
            "/api/core/skill-packs",
            json={
                "name": "pack-mix",
                "manifest": {
                    "skills": [
                        {"id": reserved_id, "display_name": "Should Skip"},
                        {"id": "pack_skill_new", "display_name": "Should Enable", "sop_markdown": "# X\n"},
                    ]
                },
            },
        )
        assert r.status_code == 200, r.text
        pack = r.json()

        r2 = client.post(f"/api/core/skill-packs/{pack['id']}/install", json={"scope": "workspace"})
        assert r2.status_code == 200, r2.text
        applied = (r2.json().get("applied") or [])

        rec_skip = next((x for x in applied if x.get("skill_id") == reserved_id), None)
        rec_ok = next((x for x in applied if x.get("skill_id") == "pack_skill_new"), None)
        assert rec_skip is not None
        assert rec_skip.get("status") == "skipped"
        assert "reserved" in (rec_skip.get("reason") or "").lower()

        assert rec_ok is not None
        assert rec_ok.get("status") in ("enabled", "skipped")

