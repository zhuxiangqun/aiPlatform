"""
Lark (飞书) Channel Adapter (渠道广度延伸批次)

Parses Lark event callback payloads into the unified ChannelMessage
format and formats responses for Lark's bot API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class LarkAdapter(ChannelAdapter):
    """飞书适配器 (机器人)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        event = raw_data.get("event") or {}
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        text = message.get("content") or ""

        # Lark content 是 JSON 字符串（如 {"text":"hello"}）
        try:
            import json

            content = json.loads(text) if isinstance(text, str) else {}
            text_value = str(content.get("text", text))
        except Exception:  # noqa: BLE001 — 非 JSON 时原样
            text_value = str(text)

        return ChannelMessage(
            message_id=str(message.get("message_id", "")),
            channel=ChannelType.LARK,
            chat_id=str(message.get("chat_id", "")),
            user_id=str((sender.get("sender_id") or {}).get("open_id", "")),
            text=text_value,
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "msg_type": "text",
            "content": {"text": response.text},
        }
