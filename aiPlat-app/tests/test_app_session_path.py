"""Session static jail, bind token, and unsigned channel verification."""

import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_session_file_rejects_escape(tmp_path: Path):
    from api.rest.routes import session_file_under_root

    root = tmp_path / "current"
    root.mkdir()
    (root / "index.html").write_text("ok", encoding="utf-8")
    assert session_file_under_root(root, "index.html") == (root / "index.html").resolve()
    assert session_file_under_root(root, "../secret.txt") is None
    assert session_file_under_root(root, "/etc/passwd") is None


def test_serve_session_path_escape_is_403(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    import importlib
    import api.rest.routes as routes

    importlib.reload(routes)
    app_dir = tmp_path / "apps" / "demo" / "current"
    app_dir.mkdir(parents=True)
    (app_dir / "index.html").write_text("home", encoding="utf-8")
    secret = tmp_path / "apps" / "secret.txt"
    secret.write_text("nope", encoding="utf-8")

    client = TestClient(routes.app)
    ok = client.get("/app/sessions/demo/index.html")
    assert ok.status_code == 200
    assert ok.text == "home"
    import asyncio

    with pytest.raises(HTTPException) as escaped:
        asyncio.run(routes.serve_app_files("demo", "../secret.txt"))
    assert escaped.value.status_code == 403
    missing = client.get("/app/sessions/missing")
    assert missing.status_code == 404


def test_assert_app_bind_requires_token(monkeypatch: pytest.MonkeyPatch):
    from api.auth import assert_app_bind_allowed

    monkeypatch.delenv("AIPLAT_APP_API_TOKEN", raising=False)
    assert_app_bind_allowed("127.0.0.1")
    with pytest.raises(SystemExit):
        assert_app_bind_allowed("0.0.0.0")
    monkeypatch.setenv("AIPLAT_APP_API_TOKEN", "t")
    assert_app_bind_allowed("0.0.0.0")


def test_unsigned_channel_fails_closed(monkeypatch: pytest.MonkeyPatch):
    from channels.slack import verify_slack_signature
    from channels.telegram import TelegramHandler

    monkeypatch.delenv("AIPLAT_CHANNEL_ALLOW_UNSIGNED", raising=False)
    assert verify_slack_signature("", "1", "body", "sig") is False
    assert TelegramHandler(secret_token="").verify_webhook(b"x", "") is False
    monkeypatch.setenv("AIPLAT_CHANNEL_ALLOW_UNSIGNED", "1")
    assert verify_slack_signature("", "1", "body", "sig") is True


def test_api_client_keeps_platform_url(monkeypatch: pytest.MonkeyPatch):
    from services.client import APIClient

    monkeypatch.setenv("AIPLAT_PLATFORM_URL", "http://platform.example")
    client = APIClient()
    assert client.base_url == "http://platform.example"
    assert APIClient(base_url="http://other").base_url == "http://other"
