"""Studio register-from-studio must fail closed without a token."""

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
        "path": "/platform/apps/register-from-studio",
        "raw_path": b"/platform/apps/register-from-studio",
        "query_string": b"",
        "headers": list(raw.items()),
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    return Request(scope)


def test_require_studio_register_auth_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_STUDIO_REGISTER_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_STUDIO_REGISTER_TOKEN", raising=False)
    monkeypatch.delenv("AIPLAT_API_KEY", raising=False)
    monkeypatch.setenv("AIPLAT_STUDIO_REGISTER_REQUIRE_AUTH", "true")
    from auth.studio_register_auth import require_studio_register_auth

    with pytest.raises(HTTPException) as ei:
        require_studio_register_auth(_request())
    assert ei.value.status_code == 401


def test_require_studio_register_auth_accepts_static_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_STUDIO_REGISTER_ALLOW_UNSIGNED", raising=False)
    monkeypatch.setenv("AIPLAT_STUDIO_REGISTER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_STUDIO_REGISTER_TOKEN", "studio-secret")
    from auth.studio_register_auth import require_studio_register_auth

    require_studio_register_auth(
        _request({"X-AiPlat-Studio-Register-Token": "studio-secret"})
    )


def test_require_studio_register_auth_accepts_api_key_fallback(monkeypatch):
    monkeypatch.delenv("AIPLAT_STUDIO_REGISTER_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_STUDIO_REGISTER_TOKEN", raising=False)
    monkeypatch.setenv("AIPLAT_STUDIO_REGISTER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_API_KEY", "plat-key")
    from auth.studio_register_auth import require_studio_register_auth

    require_studio_register_auth(_request({"X-AIPLAT-API-KEY": "plat-key"}))


def test_require_studio_register_auth_rejects_bad_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_STUDIO_REGISTER_ALLOW_UNSIGNED", raising=False)
    monkeypatch.setenv("AIPLAT_STUDIO_REGISTER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_STUDIO_REGISTER_TOKEN", "studio-secret")
    from auth.studio_register_auth import require_studio_register_auth

    with pytest.raises(HTTPException) as ei:
        require_studio_register_auth(
            _request({"X-AiPlat-Studio-Register-Token": "wrong"})
        )
    assert ei.value.status_code == 403


def test_studio_register_unsigned_allowed(monkeypatch):
    monkeypatch.setenv("AIPLAT_STUDIO_REGISTER_ALLOW_UNSIGNED", "1")
    from auth.studio_register_auth import studio_register_unsigned_allowed

    assert studio_register_unsigned_allowed() is True
