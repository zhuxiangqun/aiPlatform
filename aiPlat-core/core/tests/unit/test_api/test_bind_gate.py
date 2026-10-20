"""Core must not listen on all interfaces without a token."""

import pytest

from core.api.bind_gate import (
    CoreTokenMiddleware,
    assert_core_bind_allowed,
    is_loopback_host,
    tokens_match,
)


def test_loopback_and_token_compare():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert is_loopback_host("[::1]")
    assert not is_loopback_host("0.0.0.0")
    assert tokens_match("secret", "secret")
    assert not tokens_match("secret", "nope")
    assert not tokens_match("secret", None)


def test_non_loopback_bind_requires_token(monkeypatch):
    monkeypatch.delenv("AIPLAT_CORE_API_TOKEN", raising=False)
    monkeypatch.delenv("AIPLAT_API_KEY", raising=False)
    assert_core_bind_allowed("127.0.0.1")
    with pytest.raises(SystemExit):
        assert_core_bind_allowed("0.0.0.0")
    monkeypatch.setenv("AIPLAT_CORE_API_TOKEN", "secret")
    assert_core_bind_allowed("0.0.0.0")


def test_token_middleware_blocks_non_health(monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("AIPLAT_CORE_API_TOKEN", "secret")
    monkeypatch.delenv("AIPLAT_API_KEY", raising=False)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(CoreTokenMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/core/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/core/ping").status_code == 401
    ok = client.get(
        "/api/core/ping",
        headers={"X-AIPLAT-CORE-TOKEN": "secret"},
    )
    assert ok.status_code == 200
    bearer = client.get(
        "/api/core/ping",
        headers={"Authorization": "Bearer secret"},
    )
    assert bearer.status_code == 200
