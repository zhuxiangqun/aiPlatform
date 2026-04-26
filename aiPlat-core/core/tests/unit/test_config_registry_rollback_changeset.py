from fastapi.testclient import TestClient


def test_config_registry_rollback_emits_changeset_event():
    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")

        # publish default to ensure there's a published version
        client.post(
            "/api/core/workspace/skills/meta/config-registry/publish"
            "?asset_type=permissions_catalog&scope=workspace&tenant_id=default&channel=canary",
            json={},
        )

        client.post(
            "/api/core/workspace/skills/meta/config-registry/rollback"
            "?asset_type=permissions_catalog&scope=workspace&tenant_id=default&channel=canary",
            json={},
        )

        # verify syscall changeset event exists
        r = client.get("/api/core/syscalls/events?kind=changeset&name=config_rollback&limit=50&offset=0")
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") or []
        assert any("config_rollback" in str(it.get("name") or "") for it in items)

