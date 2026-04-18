import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_pack_publish_version_conflict_409(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post("/api/core/skill-packs", json={"name": "p1", "manifest": {"skills": ["s1"]}})
        assert r.status_code == 200, r.text
        pack = r.json()

        r2 = client.post(f"/api/core/skill-packs/{pack['id']}/publish", json={"version": "0.1.0"})
        assert r2.status_code == 200, r2.text

        # same version again -> conflict
        r3 = client.post(f"/api/core/skill-packs/{pack['id']}/publish", json={"version": "0.1.0"})
        assert r3.status_code == 409, r3.text

