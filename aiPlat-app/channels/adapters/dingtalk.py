"""
DingTalk Channel Adapter (P1-A4)

Parses DingTalk callback payloads into the unified ChannelMessage format
and formats responses for DingTalk's robot API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class DingTalkAdapter(ChannelAdapter):
    """钉钉适配器 (机器人)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        text = raw_data.get("text", {})
        sender = raw_data.get("senderId", "")
        return ChannelMessage(
            message_id=str(raw_data.get("msgId", "")),
            channel=ChannelType.DINGTALK,
            chat_id=str(raw_data.get("conversationId", sender)),
            user_id=str(sender),
            text=str(text.get("content", "")),
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "msgtype": "text",
            "text": {"content": response.text},
        }
