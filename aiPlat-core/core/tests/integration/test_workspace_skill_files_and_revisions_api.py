import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_workspace_skill_files_and_revisions(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/workspace/skills",
            json={"name": "My Skill", "category": "general", "description": "d", "template": "generic", "sop": "# SOP\nhello"},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["id"]

        # create a reference file
        skill = client.get(f"/api/core/workspace/skills/{sid}").json()
        skill_dir = Path(skill["metadata"]["filesystem"]["skill_dir"])
        (skill_dir / "references" / "readme.txt").write_text("ref", encoding="utf-8")

        files = client.get(f"/api/core/workspace/skills/{sid}/files?dir=references").json()
        assert files["total"] >= 1
        assert any(it["path"].endswith("references/readme.txt") for it in files["items"])

        content = client.get(f"/api/core/workspace/skills/{sid}/files/references/readme.txt").json()
        assert content["content"] == "ref"

        # update to create revision
        r2 = client.put(f"/api/core/workspace/skills/{sid}", json={"description": "d2"})
        assert r2.status_code == 200, r2.text

        revs = client.get(f"/api/core/workspace/skills/{sid}/revisions").json()
        assert revs["total"] >= 1

