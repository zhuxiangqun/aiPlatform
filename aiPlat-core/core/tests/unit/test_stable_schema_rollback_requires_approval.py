from fastapi.testclient import TestClient


def test_stable_schema_rollback_requires_approval():
    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        # ensure at least one publish so rollback has something to act on
        client.post(
            "/api/core/workspace/skills/meta/config-registry/publish"
            "?asset_type=skill_spec_v2_schema&scope=workspace&tenant_id=default&channel=stable",
            json={},
        )
        r = client.post(
            "/api/core/workspace/skills/meta/config-registry/rollback"
            "?asset_type=skill_spec_v2_schema&scope=workspace&tenant_id=default&channel=stable",
            json={},
        )
        assert r.status_code == 409
        detail = r.json().get("detail") if isinstance(r.json(), dict) and "detail" in r.json() else r.json()
        assert isinstance(detail, dict)
        assert detail.get("code") == "approval_required"
        assert detail.get("approval_request_id")

