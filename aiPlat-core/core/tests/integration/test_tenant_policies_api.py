import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tenant_policies_crud(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # upsert
        r = client.put(
            "/api/core/policies/tenants/t1",
            json={"policy": {"tool_policy": {"deny_tools": ["file_operations"]}}},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tenant_id"] == "t1"
        assert body["version"] == 1

        # get
        g = client.get("/api/core/policies/tenants/t1")
        assert g.status_code == 200, g.text
        assert g.json()["policy"]["tool_policy"]["deny_tools"] == ["file_operations"]

        # list
        lst = client.get("/api/core/policies/tenants", params={"limit": 10, "offset": 0})
        assert lst.status_code == 200, lst.text
        assert lst.json()["total"] >= 1

        # version conflict
        c = client.put("/api/core/policies/tenants/t1", json={"policy": {"a": 1}, "version": 999})
        assert c.status_code == 409

