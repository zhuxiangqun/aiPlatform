"""Management API must not listen on all interfaces without a token."""

import pytest

from management.auth import (
    ManagementTokenMiddleware,
    assert_bind_allowed,
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
    monkeypatch.delenv("AIPLAT_MANAGEMENT_API_TOKEN", raising=False)
    monkeypatch.delenv("AIPLAT_MANAGEMENT_API_KEY", raising=False)
    assert_bind_allowed("127.0.0.1")
    with pytest.raises(SystemExit):
        assert_bind_allowed("0.0.0.0")
    monkeypatch.setenv("AIPLAT_MANAGEMENT_API_TOKEN", "secret")
    assert_bind_allowed("0.0.0.0")


def test_token_middleware_blocks_non_health(monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("AIPLAT_MANAGEMENT_API_TOKEN", "secret")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(ManagementTokenMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/api/approval/publish")
    def publish():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.post("/api/approval/publish").status_code == 401
    ok = client.post(
        "/api/approval/publish",
        headers={"X-AIPLAT-MANAGEMENT-TOKEN": "secret"},
    )
    assert ok.status_code == 200
