"""routes.py audit/whoami/batches must not trust raw spoofable identity headers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_ROOT = Path(__file__).resolve().parents[1]
_ROUTES = (_ROOT / "api/rest/routes.py").read_text(encoding="utf-8")


class _Req:
    def __init__(self, headers):
        self.headers = headers


def test_routes_source_whoami_and_batches_use_resolve_identity():
    assert "async def platform_whoami" in _ROUTES
    assert "ident = _resolve_identity(request)" in _ROUTES
    # whoami must not invent auth_type from raw API-key presence alone
    assert 'auth_type = "api_key" if request.headers.get("X-AIPLAT-API-KEY")' not in _ROUTES
    # analysis-batches tenant isolation via gated identity
    assert _ROUTES.count('tenant_id = _resolve_identity(request).tenant_id or "default"') >= 3
    assert 'tenant_id = request.headers.get("X-AIPLAT-TENANT-ID", "default")' not in _ROUTES
    # governance audit middleware already routed (no raw ACTOR default outside _resolve_identity body)
    assert 'actor_id = request.headers.get("X-AIPLAT-ACTOR-ID", "anonymous")' not in _ROUTES


def test_whoami_ignores_spoofed_headers_outside_gate(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_IDENTITY_SECRET", raising=False)
    from api.rest.routes import _resolve_identity

    ident = _resolve_identity(_Req({
        "X-AIPLAT-TENANT-ID": "victim",
        "X-AIPLAT-ACTOR-ID": "admin",
        "X-AIPLAT-ACTOR-ROLE": "admin",
    }))
    assert ident.auth_type == "anonymous"
    assert ident.actor_id == "anonymous"
    assert ident.tenant_id == "default"


@pytest.mark.asyncio
async def test_platform_whoami_uses_resolved_identity(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_IDENTITY_SECRET", raising=False)
    from api.rest.routes import platform_whoami

    out = await platform_whoami(_Req({
        "X-AIPLAT-TENANT-ID": "victim",
        "X-AIPLAT-ACTOR-ID": "admin",
    }))
    assert out["tenant_id"] == "default"
    assert out["actor_id"] == "anonymous"
    assert out["auth_type"] == "anonymous"
