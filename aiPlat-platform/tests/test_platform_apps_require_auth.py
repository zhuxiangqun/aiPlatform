"""Platform apps modules must require API key when platform auth is configured."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# (import path, probe GET path under /api/platform/apps)
_MODULES = (
    ("apps.eval.api.router", "/code-review-gold/profiles"),
    ("apps.workbench.api.router", "/workbench/capabilities"),
    ("apps.learning.api.router", "/learning/artifacts"),
    ("apps.prompt.api.router", "/prompts/app/templates"),
    ("apps.value.api.router", "/value/default"),
    ("apps.org.api.router", "/org/goals"),
    ("apps.misc.api.router", "/browser/test/status"),
    ("apps.ontology_editor.api.router", "/ontology-editor/domains"),
)


def _client_for(module_path: str, monkeypatch) -> TestClient:
    monkeypatch.setenv("AIPLAT_API_KEY", "apps-test-key")
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)
    import importlib

    mod = importlib.import_module(module_path)
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/platform/apps")
    return TestClient(app)


@pytest.mark.parametrize("module_path,probe", _MODULES)
def test_platform_app_rejects_missing_api_key(module_path, probe, monkeypatch):
    client = _client_for(module_path, monkeypatch)
    r = client.get(f"/api/platform/apps{probe}")
    assert r.status_code == 401, f"{module_path} {probe} -> {r.status_code}"


@pytest.mark.parametrize("module_path,probe", _MODULES)
def test_platform_app_rejects_bad_api_key(module_path, probe, monkeypatch):
    client = _client_for(module_path, monkeypatch)
    r = client.get(
        f"/api/platform/apps{probe}",
        headers={"X-AIPLAT-API-KEY": "wrong"},
    )
    assert r.status_code == 403, f"{module_path} {probe} -> {r.status_code}"


@pytest.mark.parametrize("module_path,probe", _MODULES)
def test_platform_app_accepts_api_key(module_path, probe, monkeypatch):
    client = _client_for(module_path, monkeypatch)
    r = client.get(
        f"/api/platform/apps{probe}",
        headers={"X-AIPLAT-API-KEY": "apps-test-key"},
    )
    assert r.status_code != 401
    assert r.status_code != 403
