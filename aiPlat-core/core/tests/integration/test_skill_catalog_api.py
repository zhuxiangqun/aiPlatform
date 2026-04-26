import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_catalog_lists_workspace_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # create a workspace skill
        r = client.post(
            "/api/core/workspace/skills",
            headers=hdr,
            json={"name": "cat_skill", "description": "用于测试 catalog", "content": "def run():\n    return 'ok'\n"},
        )
        assert r.status_code == 200, r.text

        cat = client.get("/api/core/catalog/skills?scope=workspace&q=cat_skill", headers=hdr)
        assert cat.status_code == 200, cat.text
        items = cat.json().get("items") or []
        assert any(x.get("name") == "cat_skill" for x in items)

