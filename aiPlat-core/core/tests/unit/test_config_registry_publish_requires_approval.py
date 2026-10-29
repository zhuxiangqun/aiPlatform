"""Stable high-risk config-registry publish must fail-closed with approval_required.

GET /api/core/approvals/{id} moved to platform; assert the publish gate envelope
itself carries approval_request_id (+ optional change_id linkage when present).
"""
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
        assert isinstance(detail, dict)
        assert detail.get("code") == "approval_required"
        rid = detail.get("approval_request_id")
        assert rid
        # change_id may be attached on the gate envelope or nested metadata
        change_id = detail.get("change_id")
        if change_id is None and isinstance(detail.get("metadata"), dict):
            change_id = detail["metadata"].get("change_id")
        # Soft assert: when linkage is present it must be non-empty; when absent
        # the approval_request_id alone still proves the publish gate fired.
        if change_id is not None:
            assert change_id
