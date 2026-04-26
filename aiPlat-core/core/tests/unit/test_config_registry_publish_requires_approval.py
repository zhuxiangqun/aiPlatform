from fastapi.testclient import TestClient


def test_stable_high_risk_publish_requires_approval():
    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")

        # High-risk schema payload (missing output_schema.markdown constraint/default)
        schema_payload = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "SkillSpecV2",
            "type": "object",
            "required": ["name", "description", "category", "skill_kind", "output_schema"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "category": {"type": "string"},
                "skill_kind": {"type": "string"},
                "output_schema": {"type": "object", "default": {}},
            },
        }

        r = client.post(
            "/api/core/workspace/skills/meta/config-registry/publish"
            "?asset_type=skill_spec_v2_schema&scope=workspace&tenant_id=default&channel=stable",
            json={"payload": schema_payload, "note": "test"},
        )
        assert r.status_code == 409
        detail = r.json().get("detail") if isinstance(r.json(), dict) and "detail" in r.json() else r.json()
        # detail can be gate envelope
        assert isinstance(detail, dict)
        assert detail.get("code") == "approval_required"
        rid = detail.get("approval_request_id")
        assert rid

        # Approval request should be linked to a change_id (via syscall_events changeset)
        r2 = client.get(f"/api/core/approvals/{rid}")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("change_id")
