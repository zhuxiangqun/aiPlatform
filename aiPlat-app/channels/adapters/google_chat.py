"""
Google Chat Channel Adapter (渠道广度延伸批次)

Parses Google Chat (Hangouts Chat) event payloads into the unified
ChannelMessage format and formats responses for the Google Chat API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class GoogleChatAdapter(ChannelAdapter):
    """Google Chat 适配器 (Hangouts Chat API)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        message = raw_data.get("message") or {}
        space = raw_data.get("space") or {}
        sender = message.get("sender") or {}
        text = str(message.get("text", ""))
        # Google Chat 事件负载：message.text 含用户输入
        if not text and message.get("annotations"):
            text = str(message.get("text", ""))
        return ChannelMessage(
            message_id=str(message.get("name", "") or raw_data.get("eventTime", "")),
            channel=ChannelType.GOOGLE_CHAT,
            chat_id=str(space.get("name", "")),
            user_id=str(sender.get("name", "")),
            text=text,
            timestamp=datetime.now(),
            metadata={
                "type": raw_data.get("type", ""),
                "space_type": space.get("type", ""),
                "thread_id": (message.get("thread") or {}).get("name", ""),
                "raw": raw_data,
            },
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "text": response.text,
        }
