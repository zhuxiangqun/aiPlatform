from fastapi.testclient import TestClient


def test_config_registry_status_api_smoke():
    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.get(
            "/api/core/workspace/skills/meta/config-registry/status"
            "?asset_type=skill_spec_v2_schema&scope=workspace&tenant_id=default&channel=stable"
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("asset_type") == "skill_spec_v2_schema"

