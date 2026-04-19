import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_platform_persistence_gateway_users_tenants(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_PLATFORM_DB_PATH", str(tmp_path / "platform.sqlite3"))

    import api.rest.routes as routes

    importlib.reload(routes)

    with TestClient(routes.app) as client:
        # routes
        r = client.post("/platform/gateway/routes", json={"name": "r1", "path": "/x", "enabled": True})
        assert r.status_code == 200
        rid = r.json()["id"]

        lst = client.get("/platform/gateway/routes")
        assert lst.status_code == 200
        assert any(x["id"] == rid for x in lst.json()["routes"])

        up = client.put(f"/platform/gateway/routes/{rid}", json={"enabled": False})
        assert up.status_code == 200

        lst2 = client.get("/platform/gateway/routes", params={"enabled": True})
        assert lst2.status_code == 200
        assert all(bool(x.get("enabled")) is True for x in lst2.json()["routes"])

        # users
        u = client.post("/platform/auth/users", json={"username": "alice", "role": "admin"})
        assert u.status_code == 200
        uid = u.json()["id"]

        ul = client.get("/platform/auth/users", params={"role": "admin"})
        assert ul.status_code == 200
        assert any(x["id"] == uid for x in ul.json()["users"])

        # tenants
        t = client.post("/platform/tenants", json={"name": "t1"})
        assert t.status_code == 200
        tid = t.json()["id"]

        s = client.post(f"/platform/tenants/{tid}/suspend")
        assert s.status_code == 200
        ts = client.get("/platform/tenants", params={"status": "suspended"})
        assert ts.status_code == 200
        assert any(x["id"] == tid for x in ts.json()["tenants"])


@pytest.mark.integration
def test_platform_agents_crud_proxy(monkeypatch):
    import api.rest.routes as routes

    async def fake_core_request(method, path, *, identity, params=None, json_body=None, extra_headers=None):
        if method == "GET" and path == "/api/core/workspace/agents":
            return {"agents": [{"id": "a1", "name": "A1"}], "total": 1, "limit": 100, "offset": 0}
        if method == "POST" and path == "/api/core/workspace/agents":
            assert json_body and json_body["name"] == "N1"
            return {"id": "a_new", "status": "created", "name": "N1"}
        if method == "GET" and path == "/api/core/workspace/agents/a1":
            return {"id": "a1", "name": "A1", "agent_type": "base", "status": "ready"}
        if method == "POST" and path == "/api/core/workspace/agents/a1/execute":
            assert json_body and json_body["session_id"] == "s1"
            return {"ok": True, "run_id": "run_x", "status": "running"}
        if method == "DELETE" and path == "/api/core/workspace/agents/a1":
            return {"status": "deleted", "id": "a1"}
        raise AssertionError(f"unexpected call: {method} {path}")

    routes._core_request = fake_core_request  # type: ignore[attr-defined]

    with TestClient(routes.app) as client:
        lst = client.get("/api/v1/agents")
        assert lst.status_code == 200
        assert lst.json()["agents"][0]["id"] == "a1"

        c = client.post("/api/v1/agents", json={"name": "N1", "description": "d"})
        assert c.status_code == 200
        assert c.json()["id"] == "a_new"

        g = client.get("/api/v1/agents/a1")
        assert g.status_code == 200
        assert g.json()["agent"]["id"] == "a1"

        d = client.delete("/api/v1/agents/a1")
        assert d.status_code == 200
        assert d.json()["ok"] is True

        ex = client.post("/api/v1/agents/a1/execute", json={"input": "hi", "session_id": "s1", "context": {"tenant_id": "t1"}})
        assert ex.status_code == 200
        assert ex.json()["run_id"] == "run_x"
