from fastapi.testclient import TestClient


def test_config_registry_diff_api_smoke():
    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        # diff against a non-existent version should still return ok with null proposed
        r = client.get(
            "/api/core/workspace/skills/meta/config-registry/diff"
            "?asset_type=skill_spec_v2_schema&scope=workspace&tenant_id=default&channel=stable&from_ref=default&to_version=doesnotexist"
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "assessment" in data
        assert "diff" in data

