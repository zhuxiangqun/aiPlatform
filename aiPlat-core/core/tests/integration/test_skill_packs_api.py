import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_pack_install_materializes_workspace_skill(tmp_path, monkeypatch):
    """
    End-to-end: create pack -> install(workspace) -> workspace skill exists -> skill-md readable.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # create pack
        r = client.post(
            "/api/core/skill-packs",
            json={
                "name": "demo-pack",
                "description": "d",
                "manifest": {
                    "skills": [
                        {
                            "id": "pack_skill_hello",
                            "display_name": "Pack Skill Hello",
                            "category": "general",
                            "description": "from pack",
                            "version": "0.1.0",
                            "sop_markdown": "# Pack Skill Hello\n\nSOP demo.\n",
                        }
                    ]
                },
            },
        )
        assert r.status_code == 200, r.text
        pack = r.json()
        assert pack["id"]

        # install & apply
        r2 = client.post(f"/api/core/skill-packs/{pack['id']}/install", json={"scope": "workspace"})
        assert r2.status_code == 200, r2.text
        payload = r2.json()
        applied = payload.get("applied") or []
        assert any(x.get("skill_id") == "pack_skill_hello" and x.get("status") in ("enabled", "skipped") for x in applied)

        # workspace skill should be listed
        r3 = client.get("/api/core/workspace/skills")
        assert r3.status_code == 200, r3.text
        data = r3.json()
        skills = data.get("skills") or []
        assert any(s.get("id") == "pack_skill_hello" for s in skills)

        # SKILL.md preview endpoint
        r4 = client.get("/api/core/workspace/skills/pack_skill_hello/skill-md")
        assert r4.status_code == 200, r4.text
        md = r4.json()
        assert "SKILL.md" in md.get("path", "") or md.get("content", "").startswith("---")
        assert "skill_pack" in md.get("content", "")

