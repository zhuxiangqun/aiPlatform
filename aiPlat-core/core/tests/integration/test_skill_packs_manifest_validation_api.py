import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_pack_manifest_validation_400(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # manifest must be object
        r = client.post("/api/core/skill-packs", json={"name": "bad", "manifest": "not-object"})
        # Pydantic validation happens before our handler (422 is expected here)
        assert r.status_code == 422, r.text

        # manifest.skills must be array
        r2 = client.post("/api/core/skill-packs", json={"name": "bad2", "manifest": {"skills": {"id": "x"}}})
        assert r2.status_code == 400, r2.text

        # skills item must have id
        r3 = client.post("/api/core/skill-packs", json={"name": "bad3", "manifest": {"skills": [{"display_name": "x"}]}})
        assert r3.status_code == 400, r3.text
