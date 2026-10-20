"""Slack KB webhook must fail closed without a valid signing secret."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest


def test_require_slack_request_rejects_missing_secret(monkeypatch):
    monkeypatch.delenv("AIPLAT_SLACK_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("AIPLAT_CHANNEL_ALLOW_UNSIGNED", raising=False)
    from auth.slack_signature import require_slack_request

    with pytest.raises(ValueError, match="signing secret"):
        require_slack_request({}, b"text=hello")


def test_require_slack_request_accepts_valid_signature(monkeypatch):
    secret = "test_signing_secret"
    monkeypatch.setenv("AIPLAT_SLACK_SIGNING_SECRET", secret)
    monkeypatch.delenv("AIPLAT_CHANNEL_ALLOW_UNSIGNED", raising=False)
    from auth.slack_signature import require_slack_request

    ts = str(int(time.time()))
    body = "text=hello"
    base = f"v0:{ts}:{body}".encode("utf-8")
    sig = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    require_slack_request(
        {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig},
        body.encode("utf-8"),
    )


def test_require_slack_request_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("AIPLAT_SLACK_SIGNING_SECRET", "test_signing_secret")
    monkeypatch.delenv("AIPLAT_CHANNEL_ALLOW_UNSIGNED", raising=False)
    from auth.slack_signature import require_slack_request

    ts = str(int(time.time()))
    with pytest.raises(ValueError, match="invalid slack signature"):
        require_slack_request(
            {
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=deadbeef",
            },
            b"text=hello",
        )


def test_widget_js_escapes_answer():
    import asyncio

    from api.routers.kb_integration import kb_widget_js

    resp = asyncio.run(kb_widget_js())
    body = bytes(resp.body).decode("utf-8")
    assert "function esc(" in body
    assert "esc(j.answer" in body
    assert "ans.innerHTML = '<strong>回答：</strong><br>' + (j.answer" not in body
