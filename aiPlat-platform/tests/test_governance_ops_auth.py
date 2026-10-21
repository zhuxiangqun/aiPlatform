"""Governance jobs/agents mutators must fail closed without a token."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = {k.lower().encode(): v.encode() for k, v in (headers or {}).items()}
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/governance/jobs",
        "raw_path": b"/governance/jobs",
        "query_string": b"",
        "headers": list(raw.items()),
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    return Request(scope)


def test_require_governance_ops_auth_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_GOVERNANCE_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_GOVERNANCE_OPS_TOKEN", raising=False)
    monkeypatch.delenv("AIPLAT_API_KEY", raising=False)
    monkeypatch.setenv("AIPLAT_GOVERNANCE_OPS_REQUIRE_AUTH", "true")
    from auth.governance_ops_auth import require_governance_ops_auth

    with pytest.raises(HTTPException) as ei:
        require_governance_ops_auth(_request())
    assert ei.value.status_code == 401


def test_require_governance_ops_auth_accepts_static_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_GOVERNANCE_ALLOW_UNSIGNED", raising=False)
    monkeypatch.setenv("AIPLAT_GOVERNANCE_OPS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_GOVERNANCE_OPS_TOKEN", "gov-secret")
    from auth.governance_ops_auth import require_governance_ops_auth

    require_governance_ops_auth(
        _request({"X-AiPlat-Governance-Ops-Token": "gov-secret"})
    )


def test_require_governance_ops_auth_accepts_api_key_fallback(monkeypatch):
    monkeypatch.delenv("AIPLAT_GOVERNANCE_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_GOVERNANCE_OPS_TOKEN", raising=False)
    monkeypatch.setenv("AIPLAT_GOVERNANCE_OPS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_API_KEY", "plat-key")
    from auth.governance_ops_auth import require_governance_ops_auth

    require_governance_ops_auth(_request({"X-AIPLAT-API-KEY": "plat-key"}))


def test_require_governance_ops_auth_rejects_bad_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_GOVERNANCE_ALLOW_UNSIGNED", raising=False)
    monkeypatch.setenv("AIPLAT_GOVERNANCE_OPS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_GOVERNANCE_OPS_TOKEN", "gov-secret")
    from auth.governance_ops_auth import require_governance_ops_auth

    with pytest.raises(HTTPException) as ei:
        require_governance_ops_auth(
            _request({"X-AiPlat-Governance-Ops-Token": "wrong"})
        )
    assert ei.value.status_code == 403


def test_governance_ops_unsigned_allowed(monkeypatch):
    monkeypatch.setenv("AIPLAT_GOVERNANCE_ALLOW_UNSIGNED", "1")
    from auth.governance_ops_auth import governance_ops_unsigned_allowed

    assert governance_ops_unsigned_allowed() is True
