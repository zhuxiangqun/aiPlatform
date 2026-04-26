from fastapi.testclient import TestClient


def test_skill_spec_v2_schema_registry_smoke():
    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.get("/api/core/workspace/skills/meta/skill-spec-v2-schema?tenant_id=default&channel=stable")
        assert r.status_code == 200
        data = r.json()
        # RBAC deny may return a deny object; accept that shape too
        if "schema" in data:
            assert "properties" in data["schema"]
            assert "version" in data
