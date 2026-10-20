"""FDE platform routes must require API key when platform auth is configured."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def fde_client(monkeypatch):
    monkeypatch.setenv("AIPLAT_API_KEY", "fde-test-key")
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)
    from apps.fde.api.router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/platform/apps")
    # Auth-only: handler may raise after the dependency succeeds.
    return TestClient(app, raise_server_exceptions=False)


def test_fde_mutating_route_rejects_missing_api_key(fde_client):
    r = fde_client.post("/api/platform/apps/fde/templates/register", json={})
    assert r.status_code == 401


def test_fde_mutating_route_rejects_bad_api_key(fde_client):
    r = fde_client.post(
        "/api/platform/apps/fde/templates/register",
        json={},
        headers={"X-AIPLAT-API-KEY": "wrong"},
    )
    assert r.status_code == 403


def test_fde_mutating_route_accepts_api_key(fde_client):
    r = fde_client.post(
        "/api/platform/apps/fde/templates/register",
        json={"template_id": "t1", "path": "/tmp/x.md"},
        headers={"X-AIPLAT-API-KEY": "fde-test-key"},
    )
    # Auth passed — handler may still fail on missing core deps.
    assert r.status_code != 401
    assert r.status_code != 403


def test_fde_dev_mode_without_api_key_env(monkeypatch):
    monkeypatch.delenv("AIPLAT_API_KEY", raising=False)
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)
    from apps.fde.api.router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/platform/apps")
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/platform/apps/fde/templates/register", json={})
    assert r.status_code != 401
    assert r.status_code != 403
