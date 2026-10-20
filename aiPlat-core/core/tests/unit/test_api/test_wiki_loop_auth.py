"""Wiki loop webhook/trigger CRUD must fail closed without a token."""

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
        "path": "/wiki/loop/webhook",
        "raw_path": b"/wiki/loop/webhook",
        "query_string": b"",
        "headers": list(raw.items()),
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    return Request(scope)


def test_require_wiki_loop_auth_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_WIKI_LOOP_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_WIKI_LOOP_WEBHOOK_TOKEN", raising=False)
    monkeypatch.delenv("AIPLAT_API_KEY", raising=False)
    monkeypatch.setenv("AIPLAT_WIKI_LOOP_REQUIRE_AUTH", "true")
    from core.api.wiki_loop_auth import require_wiki_loop_auth

    with pytest.raises(HTTPException) as ei:
        require_wiki_loop_auth(_request())
    assert ei.value.status_code == 401


def test_require_wiki_loop_auth_accepts_static_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_WIKI_LOOP_ALLOW_UNSIGNED", raising=False)
    monkeypatch.setenv("AIPLAT_WIKI_LOOP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_WIKI_LOOP_WEBHOOK_TOKEN", "loop-secret")
    from core.api.wiki_loop_auth import require_wiki_loop_auth

    require_wiki_loop_auth(_request({"X-AiPlat-Wiki-Loop-Token": "loop-secret"}))


def test_require_wiki_loop_auth_rejects_bad_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_WIKI_LOOP_ALLOW_UNSIGNED", raising=False)
    monkeypatch.setenv("AIPLAT_WIKI_LOOP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_WIKI_LOOP_WEBHOOK_TOKEN", "loop-secret")
    from core.api.wiki_loop_auth import require_wiki_loop_auth

    with pytest.raises(HTTPException) as ei:
        require_wiki_loop_auth(_request({"X-AiPlat-Wiki-Loop-Token": "wrong"}))
    assert ei.value.status_code == 403


def test_require_wiki_loop_auth_falls_back_to_api_key(monkeypatch):
    monkeypatch.delenv("AIPLAT_WIKI_LOOP_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("AIPLAT_WIKI_LOOP_WEBHOOK_TOKEN", raising=False)
    monkeypatch.setenv("AIPLAT_WIKI_LOOP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AIPLAT_API_KEY", "core-key")
    from core.api.wiki_loop_auth import require_wiki_loop_auth

    require_wiki_loop_auth(_request({"X-AIPLAT-API-KEY": "core-key"}))


def test_wiki_loop_unsigned_allowed(monkeypatch):
    monkeypatch.setenv("AIPLAT_WIKI_LOOP_ALLOW_UNSIGNED", "1")
    from core.api.wiki_loop_auth import require_wiki_loop_auth, wiki_loop_unsigned_allowed

    assert wiki_loop_unsigned_allowed() is True
    require_wiki_loop_auth(_request())
