"""
QQ Channel Adapter (渠道广度延伸批次 14→18)

Parses QQ (Tencent) bot message payloads into the unified ChannelMessage
format and formats responses for QQ bot API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class QQAdapter(ChannelAdapter):
    """QQ 适配器 (QQ 机器人)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # QQ 机器人回调：{"event":{"message":{"id":"...","content":"...","chat_id":"...","from_id":"..."}}}
        event = raw_data.get("event") or raw_data
        message = event.get("message") or raw_data
        text = str(message.get("content", "") or message.get("text", ""))
        chat_id = str(message.get("chat_id", "") or message.get("group_openid", "") or message.get("from_id", ""))
        user = str(message.get("from_id", "") or message.get("sender_openid", ""))
        return ChannelMessage(
            message_id=str(message.get("id", "") or event.get("id", "")),
            channel=ChannelType.QQ,
            chat_id=chat_id,
            user_id=user,
            text=text,
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "msg_type": "text",
            "content": response.text,
        }
