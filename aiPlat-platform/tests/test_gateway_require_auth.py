"""Gateway execute/webhook must fail closed without a token."""

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
        "path": "/platform/gateway/gateway/execute",
        "raw_path": b"/platform/gateway/gateway/execute",
        "query_string": b"",
        "headers": list(raw.items()),
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_require_gateway_execute_auth_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_GATEWAY_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv("AIPLAT_GATEWAY_REQUIRE_AUTH", "true")
    from auth.gateway_auth import require_gateway_execute_auth

    with pytest.raises(HTTPException) as ei:
        await require_gateway_execute_auth(_request())
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_require_gateway_execute_auth_accepts_static_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_GATEWAY_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.setenv("AIPLAT_GATEWAY_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_GATEWAY_TOKEN", "gw-secret")
    from auth.gateway_auth import require_gateway_execute_auth

    await require_gateway_execute_auth(
        _request({"X-AiPlat-Gateway-Token": "gw-secret"})
    )


@pytest.mark.asyncio
async def test_require_gateway_execute_auth_rejects_bad_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_GATEWAY_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.setenv("AIPLAT_GATEWAY_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_GATEWAY_TOKEN", "gw-secret")
    from auth.gateway_auth import require_gateway_execute_auth

    with pytest.raises(HTTPException) as ei:
        await require_gateway_execute_auth(
            _request({"X-AiPlat-Gateway-Token": "wrong"})
        )
    assert ei.value.status_code == 403


def test_require_gateway_admin_fail_closed_without_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_GATEWAY_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_GATEWAY_ADMIN_TOKEN", raising=False)
    from auth.gateway_auth import require_gateway_admin

    with pytest.raises(HTTPException) as ei:
        require_gateway_admin(_request())
    assert ei.value.status_code == 503


def test_gateway_unsigned_allowed_via_dev_mode(monkeypatch):
    monkeypatch.delenv("AIPLAT_GATEWAY_ALLOW_UNSIGNED", raising=False)
    monkeypatch.setenv("AIPLAT_PLATFORM_DEV_MODE", "1")
    from auth.gateway_auth import gateway_unsigned_allowed

    assert gateway_unsigned_allowed() is True
