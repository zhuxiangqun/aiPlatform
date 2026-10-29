"""HTTP contract: POST /platform/permissions/grant|revoke via platform router."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_permission_grant_and_revoke_via_http(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))

    from api.routers import permissions as perm_routes
    from auth.deps import require_admin, require_auth
    from core.api.core_facade import Permission
    from core.api.facades import security_facade as sf
    import core.apps.tools.permission as perm_mod

    pm = perm_mod.PermissionManager()
    perm_mod._global_permission_manager = pm
    monkeypatch.setattr(sf, "get_permission_manager", lambda: pm)

    app = FastAPI()
    app.dependency_overrides[require_auth] = lambda: "admin"
    app.dependency_overrides[require_admin] = lambda: "admin"
    app.include_router(perm_routes.router, prefix="/api")

    with TestClient(app) as client:
        grant = client.post(
            "/api/platform/permissions/permissions/grant",
            json={
                "user_id": "u1",
                "resource_id": "calculator",
                "permission": "execute",
                "granted_by": "admin",
            },
        )
        assert grant.status_code == 200, grant.text
        body = grant.json()
        assert body.get("status") == "granted"
        assert pm.check_permission("u1", "calculator", Permission.EXECUTE) is True

        listed = client.get("/api/platform/permissions/permissions/users/u1")
        assert listed.status_code == 200, listed.text
        perms = (listed.json().get("permissions") or {}).get("calculator") or []
        assert "execute" in perms

        revoke = client.post(
            "/api/platform/permissions/permissions/revoke",
            json={"user_id": "u1", "resource_id": "calculator"},
        )
        assert revoke.status_code == 200, revoke.text
        assert revoke.json().get("status") == "revoked"
        assert pm.check_permission("u1", "calculator", Permission.EXECUTE) is False
