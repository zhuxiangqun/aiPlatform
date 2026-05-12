"""
Slack Handler — Channel adapter for Slack webhooks, events, and commands.

Handles Slack signature verification, URL verification challenge, slash commands,
and Events API message events. Forwards normalized messages to the channel
dispatcher for routing to platform/core API.

Migrated from aiPlat-core/core/api/routers/gateway.py per architecture contract:
channel adaptation belongs in app layer (docs/index.md §Layer 3).
"""

import hashlib
import hmac
import json
import time as _time
from typing import Any, Callable, Dict, Optional

from .adapter import ChannelMessage, ChannelResponse, ChannelDispatcher, channel_dispatcher


def verify_slack_signature(signing_secret: str, timestamp: str, body: str, signature: str) -> bool:
    """Verify Slack request signature (HMAC-SHA256).

    Returns True if valid or if signing_secret is not configured.
    Raises ValueError with 'stale' code if timestamp is outside 5-minute window.
    Raises ValueError with 'invalid' code if signature doesn't match.
    """
    if not signing_secret:
        return True

    try:
        ts_i = int(timestamp)
    except (ValueError, TypeError):
        raise ValueError("invalid slack timestamp")

    if abs(int(_time.time()) - ts_i) > 60 * 5:
        raise ValueError("stale slack request: timestamp outside 5-minute window")

    base = f"v0:{timestamp}:{body}".encode("utf-8")
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"), base, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise ValueError("invalid slack signature")

    return True


def parse_slash_command(raw_body: bytes) -> Dict[str, Optional[str]]:
    """Parse Slack slash command form-encoded body."""
    import urllib.parse
    form = urllib.parse.parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)

    def _one(k: str) -> Optional[str]:
        v = form.get(k)
        return str(v[0]) if v else None

    return {
        "user_id": _one("user_id"),
        "text": _one("text") or "",
        "response_url": _one("response_url"),
        "team_id": _one("team_id"),
        "channel_id": _one("channel_id"),
    }


class SlackHandler:
    """Slack message processor — receives webhook events, normalizes, dispatches."""

    def __init__(self, signing_secret: str = ""):
        self.signing_secret = signing_secret
        self._dispatcher = channel_dispatcher
        self._message_handler: Optional[Callable] = None

    # ── Signature verification ─────────────────────────────────────

    def verify_request(
        self, headers: Dict[str, str], raw_body: bytes
    ) -> bool:
        """Verify a Slack request from HTTP headers and raw body."""
        ts = headers.get("x-slack-request-timestamp") or headers.get(
            "X-Slack-Request-Timestamp", ""
        )
        sig = headers.get("x-slack-signature") or headers.get(
            "X-Slack-Signature", ""
        )
        return verify_slack_signature(
            self.signing_secret, ts, raw_body.decode("utf-8"), sig
        )

    # ── Event handling ─────────────────────────────────────────────

    def handle_url_verification(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Slack URL verification challenge."""
        if body.get("type") == "url_verification" and body.get("challenge"):
            return {"challenge": body["challenge"]}
        return {}

    def handle_event(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Slack Events API event (message, app_mention)."""
        if body.get("type") != "event_callback":
            return {"ok": True}

        event = body.get("event") if isinstance(body.get("event"), dict) else {}
        if not event or event.get("bot_id"):
            return {"ok": True}  # skip bot messages

        channel_msg = self._dispatcher.dispatch("slack", event)
        if self._message_handler:
            response = self._message_handler(channel_msg)
            return self._dispatcher.reply("slack", channel_msg.message_id, response.text)

        return {"ok": True}

    def handle_command(
        self, parsed: Dict[str, Optional[str]]
    ) -> Dict[str, Any]:
        """Handle Slack slash command."""
        text = parsed.get("text") or ""
        user_id = parsed.get("user_id") or "unknown"

        channel_msg = ChannelMessage(
            message_id=user_id,
            channel="slack",
            user_id=user_id,
            text=text,
            raw=parsed,
        )

        if self._message_handler:
            response = self._message_handler(channel_msg)
            return {"ok": True, "response_type": "in_channel", "text": response.text}

        return {"ok": True, "response_type": "ephemeral", "text": f"Command received: {text}"}

    def handle_interaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Slack interaction (button clicks, modals)."""
        return {"ok": True}

    # ── Callback registration ──────────────────────────────────────

    def set_message_handler(
        self, handler: Callable[[ChannelMessage], ChannelResponse]
    ) -> None:
        self._message_handler = handler


slack_handler = SlackHandler()
