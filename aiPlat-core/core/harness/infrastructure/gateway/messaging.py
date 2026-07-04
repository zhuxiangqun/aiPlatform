"""
Enterprise Messaging Gateway — Feishu / WeCom / Slack adapters.

Provides unified interface for sending notifications to enterprise channels.
Config-driven, zero new dependencies (uses aiohttp/urllib built-ins).

hermes-agent parity: gateway/ — multi-platform messaging gateway
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class GatewayChannel(Enum):
    FEISHU = "feishu"
    WECOM = "wecom"
    SLACK = "slack"


class MessageLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class GatewayMessage:
    """Unified message format for all channels."""
    title: str
    content: str
    level: MessageLevel = MessageLevel.INFO
    url: Optional[str] = None
    fields: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class SendResult:
    success: bool
    channel: GatewayChannel
    error: Optional[str] = None
    response_status: Optional[int] = None


# ── Abstract Base ────────────────────────────────────────────────────────────

class BaseMessagingAdapter(ABC):
    """Abstract adapter for messaging channels."""

    @abstractmethod
    async def send(self, message: GatewayMessage) -> SendResult:
        """Send a message to the channel."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if all required env vars are set."""
        ...

    @property
    @abstractmethod
    def channel(self) -> GatewayChannel:
        """Return the channel this adapter handles."""
        ...


# ── Feishu (Lark) Adapter ────────────────────────────────────────────────────

class FeishuAdapter(BaseMessagingAdapter):
    """
    Send messages via Feishu/Lark webhook.

    Env vars:
        AIPLAT_FEISHU_WEBHOOK — full webhook URL
        AIPLAT_FEISHU_SECRET — (optional) signing secret
    """

    @property
    def channel(self) -> GatewayChannel:
        return GatewayChannel.FEISHU

    def is_configured(self) -> bool:
        return bool(os.getenv("AIPLAT_FEISHU_WEBHOOK"))

    def _sign(self, timestamp: int) -> Optional[str]:
        secret = os.getenv("AIPLAT_FEISHU_SECRET", "")
        if not secret:
            return None

        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return hmac_code.hex()

    async def send(self, message: GatewayMessage) -> SendResult:
        webhook = os.getenv("AIPLAT_FEISHU_WEBHOOK", "")
        if not webhook:
            return SendResult(success=False, channel=GatewayChannel.FEISHU, error="webhook not configured")

        color_map = {
            MessageLevel.INFO: "blue",
            MessageLevel.WARNING: "yellow",
            MessageLevel.ERROR: "red",
            MessageLevel.SUCCESS: "green",
        }
        level_color = color_map.get(message.level, "blue")

        body = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": message.title},
                    "template": level_color,
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": message.content,
                    },
                ],
            },
        }

        if message.fields:
            fields_list = [
                {"tag": "markdown", "content": f"**{k}**: {v}"}
                for k, v in message.fields.items()
            ]
            body["card"]["elements"].extend(fields_list)

        if message.url:
            body["card"]["elements"].append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "View Details"},
                    "url": message.url,
                    "type": "default",
                }],
            })

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                ts = int(time.time())
                sign = self._sign(ts)
                if sign:
                    headers["X-Lark-Signature"] = sign
                    headers["X-Lark-Request-Timestamp"] = str(ts)

                async with session.post(webhook, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    code = result.get("code", -1)
                    if code == 0:
                        return SendResult(success=True, channel=GatewayChannel.FEISHU, response_status=200)
                    return SendResult(
                        success=False, channel=GatewayChannel.FEISHU,
                        error=f"Feishu API error: code={code}, msg={result.get('msg', '')}",
                        response_status=code,
                    )
        except ImportError:
            # Fallback to urllib
            data = json.dumps(body).encode("utf-8")
            req = Request(webhook, data=data, headers={"Content-Type": "application/json"}, method="POST")
            try:
                resp = urlopen(req, timeout=10)
                result = json.loads(resp.read())
                code = result.get("code", -1)
                if code == 0:
                    return SendResult(success=True, channel=GatewayChannel.FEISHU, response_status=200)
                return SendResult(success=False, channel=GatewayChannel.FEISHU, error=f"code={code}")
            except Exception as e:
                return SendResult(success=False, channel=GatewayChannel.FEISHU, error=str(e))
        except Exception as e:
            logger.error("FeishuAdapter: send failed: %s", e)
            return SendResult(success=False, channel=GatewayChannel.FEISHU, error=str(e))


# ── WeCom (企业微信) Adapter ──────────────────────────────────────────────────

class WeComAdapter(BaseMessagingAdapter):
    """
    Send messages via WeCom (企业微信) webhook.

    Env vars:
        AIPLAT_WECOM_WEBHOOK — full webhook URL
    """

    @property
    def channel(self) -> GatewayChannel:
        return GatewayChannel.WECOM

    def is_configured(self) -> bool:
        return bool(os.getenv("AIPLAT_WECOM_WEBHOOK"))

    async def send(self, message: GatewayMessage) -> SendResult:
        webhook = os.getenv("AIPLAT_WECOM_WEBHOOK", "")
        if not webhook:
            return SendResult(success=False, channel=GatewayChannel.WECOM, error="webhook not configured")

        level_emoji = {
            MessageLevel.INFO: "ℹ️",
            MessageLevel.WARNING: "⚠️",
            MessageLevel.ERROR: "❌",
            MessageLevel.SUCCESS: "✅",
        }
        emoji = level_emoji.get(message.level, "ℹ️")

        fields_text = ""
        if message.fields:
            fields_text = "\n".join(f"> {k}: {v}" for k, v in message.fields.items())

        content = f"{emoji} **{message.title}**\n{message.content}"
        if fields_text:
            content += f"\n{fields_text}"
        if message.url:
            content += f"\n[查看详情]({message.url})"

        body = {
            "msgtype": "markdown",
            "markdown": {
                "content": content,
            },
        }

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook, json=body, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    errcode = result.get("errcode", -1)
                    if errcode == 0:
                        return SendResult(success=True, channel=GatewayChannel.WECOM, response_status=200)
                    return SendResult(
                        success=False, channel=GatewayChannel.WECOM,
                        error=f"WeCom API error: errcode={errcode}, errmsg={result.get('errmsg', '')}",
                    )
        except ImportError:
            data = json.dumps(body).encode("utf-8")
            req = Request(webhook, data=data, headers={"Content-Type": "application/json"}, method="POST")
            try:
                resp = urlopen(req, timeout=10)
                result = json.loads(resp.read())
                if result.get("errcode", -1) == 0:
                    return SendResult(success=True, channel=GatewayChannel.WECOM, response_status=200)
                return SendResult(success=False, channel=GatewayChannel.WECOM, error=str(result))
            except Exception as e:
                return SendResult(success=False, channel=GatewayChannel.WECOM, error=str(e))
        except Exception as e:
            logger.error("WeComAdapter: send failed: %s", e)
            return SendResult(success=False, channel=GatewayChannel.WECOM, error=str(e))


# ── Slack Adapter ────────────────────────────────────────────────────────────

class SlackAdapter(BaseMessagingAdapter):
    """
    Send messages via Slack webhook or Bot Token.

    Env vars:
        AIPLAT_SLACK_BOT_TOKEN — Slack Bot token (xoxb-...)
        AIPLAT_SLACK_CHANNEL — target channel (e.g. #alerts)
        AIPLAT_SLACK_WEBHOOK — (alternative) incoming webhook URL
    """

    @property
    def channel(self) -> GatewayChannel:
        return GatewayChannel.SLACK

    def is_configured(self) -> bool:
        return bool(os.getenv("AIPLAT_SLACK_BOT_TOKEN") or os.getenv("AIPLAT_SLACK_WEBHOOK"))

    async def send(self, message: GatewayMessage) -> SendResult:
        bot_token = os.getenv("AIPLAT_SLACK_BOT_TOKEN", "")
        webhook = os.getenv("AIPLAT_SLACK_WEBHOOK", "")
        channel = os.getenv("AIPLAT_SLACK_CHANNEL", "#aiplat-alerts")

        if not bot_token and not webhook:
            return SendResult(success=False, channel=GatewayChannel.SLACK, error="no token or webhook configured")

        color_map = {
            MessageLevel.INFO: "#36a64f",
            MessageLevel.WARNING: "#ffcc00",
            MessageLevel.ERROR: "#ff0000",
            MessageLevel.SUCCESS: "#36a64f",
        }
        color = color_map.get(message.level, "#36a64f")

        fields = [{"title": k, "value": v, "short": True} for k, v in message.fields.items()]

        body = {
            "attachments": [{
                "color": color,
                "title": message.title,
                "text": message.content,
                "fields": fields,
                "footer": "aiPlat Gateway",
                "ts": int(message.timestamp),
            }],
        }

        if message.url:
            body["attachments"][0]["title_link"] = message.url

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                if webhook:
                    url = webhook
                    async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            return SendResult(success=True, channel=GatewayChannel.SLACK, response_status=200)
                        return SendResult(success=False, channel=GatewayChannel.SLACK, error=f"HTTP {resp.status}")
                else:
                    url = "https://slack.com/api/chat.postMessage"
                    headers = {
                        "Authorization": f"Bearer {bot_token}",
                        "Content-Type": "application/json",
                    }
                    slack_body = {
                        "channel": channel,
                        "attachments": body["attachments"],
                    }
                    async with session.post(url, json=slack_body, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        result = await resp.json()
                        if result.get("ok"):
                            return SendResult(success=True, channel=GatewayChannel.SLACK, response_status=200)
                        return SendResult(
                            success=False, channel=GatewayChannel.SLACK,
                            error=result.get("error", "unknown"),
                        )
        except Exception as e:
            logger.error("SlackAdapter: send failed: %s", e)
            return SendResult(success=False, channel=GatewayChannel.SLACK, error=str(e))


# ── Messaging Gateway ────────────────────────────────────────────────────────

class MessagingGateway:
    """
    Unified gateway for sending notifications to all configured channels.

    Usage:
        gateway = MessagingGateway()
        await gateway.broadcast(GatewayMessage(
            title="Pipeline Failed",
            content="Stage 'qa' failed with exit code 1.",
            level=MessageLevel.ERROR,
            fields={"run_id": "abc123", "stage": "qa"},
        ))
    """

    def __init__(self):
        self._adapters: Dict[GatewayChannel, BaseMessagingAdapter] = {}
        self._register_if_configured(GatewayChannel.FEISHU, FeishuAdapter())
        self._register_if_configured(GatewayChannel.WECOM, WeComAdapter())
        self._register_if_configured(GatewayChannel.SLACK, SlackAdapter())

    def _register_if_configured(self, channel: GatewayChannel, adapter: BaseMessagingAdapter):
        if adapter.is_configured():
            self._adapters[channel] = adapter
            logger.info("MessagingGateway: %s adapter configured", channel.value)
        else:
            logger.debug("MessagingGateway: %s adapter not configured", channel.value)

    async def send(self, message: GatewayMessage, channel: Optional[GatewayChannel] = None) -> List[SendResult]:
        """Send to a specific channel, or all if channel=None."""
        targets = [self._adapters[channel]] if channel else list(self._adapters.values())
        results: List[SendResult] = []
        for adapter in targets:
            try:
                result = await adapter.send(message)
                results.append(result)
            except Exception as e:
                results.append(SendResult(success=False, channel=adapter.channel, error=str(e)))
        return results

    async def broadcast(self, message: GatewayMessage) -> List[SendResult]:
        """Send to all configured channels."""
        return await self.send(message)

    def get_configured_channels(self) -> List[str]:
        """Return list of configured channel names."""
        return [ch.value for ch in self._adapters]

    def get_stats(self) -> Dict[str, Any]:
        """Return gateway configuration summary."""
        return {
            "configured_channels": self.get_configured_channels(),
            "feishu": FeishuAdapter().is_configured(),
            "wecom": WeComAdapter().is_configured(),
            "slack": SlackAdapter().is_configured(),
        }


# ── Global Singleton ──────────────────────────────────────────────────────────

_messaging_gateway: Optional[MessagingGateway] = None


def get_messaging_gateway() -> MessagingGateway:
    """Get or create the global MessagingGateway singleton."""
    global _messaging_gateway
    if _messaging_gateway is None:
        _messaging_gateway = MessagingGateway()
    return _messaging_gateway


def reset_messaging_gateway():
    """Reset the global singleton (for testing)."""
    global _messaging_gateway
    _messaging_gateway = None
