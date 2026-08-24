"""
LINE Channel Adapter (渠道广度延伸批次 10→14)

Parses LINE Messaging API webhook events into the unified ChannelMessage
format and formats responses for LINE's Reply API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class LineAdapter(ChannelAdapter):
    """LINE 适配器 (Messaging API)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # LINE webhook: {"events":[{"type":"message","replyToken":"...",
        #   "source":{"userId":"..."},"message":{"id":"...","type":"text","text":"..."}}]}
        events = raw_data.get("events") or []
        event = events[0] if events else raw_data
        message = event.get("message") or {}
        source = event.get("source") or {}
        text = str(message.get("text", "") or "")
        if message.get("type") != "text":
            text = f"[{message.get('type', 'unknown')}] {text}"
        return ChannelMessage(
            message_id=str(message.get("id", "") or event.get("replyToken", "")),
            channel=ChannelType.LINE,
            chat_id=str(source.get("groupId", "") or source.get("userId", "")),
            user_id=str(source.get("userId", "")),
            text=text,
            timestamp=datetime.now(),
            metadata={"reply_token": event.get("replyToken", ""), "raw": raw_data},
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "replyToken": response.message_id,
            "messages": [{"type": "text", "text": response.text}],
        }
