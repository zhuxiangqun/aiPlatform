"""Slack request signature checks for platform webhooks.

Fail closed when ``AIPLAT_SLACK_SIGNING_SECRET`` is unset, unless
``AIPLAT_CHANNEL_ALLOW_UNSIGNED`` is explicitly enabled (local only).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional


def channel_unsigned_allowed() -> bool:
    return os.getenv("AIPLAT_CHANNEL_ALLOW_UNSIGNED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
    )


def slack_signing_secret() -> Optional[str]:
    tok = (os.getenv("AIPLAT_SLACK_SIGNING_SECRET") or "").strip()
    return tok or None


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: str,
    signature: str,
) -> bool:
    """Verify Slack HMAC-SHA256 signature (v0=…). Raises ValueError on failure."""
    if not signing_secret:
        return channel_unsigned_allowed()
    try:
        ts_i = int(timestamp)
    except (ValueError, TypeError) as e:
        raise ValueError("invalid slack timestamp") from e
    if abs(int(time.time()) - ts_i) > 60 * 5:
        raise ValueError("stale slack request: timestamp outside 5-minute window")
    base = f"v0:{timestamp}:{body}".encode("utf-8")
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"), base, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise ValueError("invalid slack signature")
    return True


def require_slack_request(headers: dict, raw_body: bytes) -> None:
    """Raise ValueError when the Slack request must be rejected."""
    secret = slack_signing_secret()
    if not secret:
        if channel_unsigned_allowed():
            return
        raise ValueError("slack signing secret not configured")
    ts = headers.get("x-slack-request-timestamp") or headers.get(
        "X-Slack-Request-Timestamp", ""
    )
    sig = headers.get("x-slack-signature") or headers.get("X-Slack-Signature", "")
    verify_slack_signature(secret, str(ts), raw_body.decode("utf-8"), str(sig))
