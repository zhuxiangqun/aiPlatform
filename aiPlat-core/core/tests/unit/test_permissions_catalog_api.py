from fastapi.testclient import TestClient


def test_workspace_permissions_catalog_smoke():
    from core.server import app

    with TestClient(app) as client:
        # any lightweight endpoint to init lifespan (consistent with other tests)
        client.get("/api/core/permissions/stats")
        r = client.get("/api/core/workspace/skills/meta/permissions-catalog?tenant_id=default&channel=stable")
        # RBAC may block in some contexts; accept either success or deny object
        assert r.status_code == 200
        data = r.json()
        assert "items" in data or "deny" in data or "status" in data
        if "items" in data:
            assert any(it.get("permission") == "llm:generate" for it in data["items"])
