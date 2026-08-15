"""
WeCom (企业微信) Channel Adapter (P1-A4)

Parses WeCom callback XML/JSON payloads into the unified ChannelMessage
format and formats responses for WeCom's API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class WeComAdapter(ChannelAdapter):
    """企业微信适配器"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        text = raw_data.get("Text", {})
        return ChannelMessage(
            message_id=str(raw_data.get("MsgId", "")),
            channel=ChannelType.WECHAT,
            chat_id=str(raw_data.get("FromUserName", "")),
            user_id=str(raw_data.get("FromUserName", "")),
            text=str(text.get("Content", "")),
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "touser": "@all",
            "msgtype": "text",
            "text": {"content": response.text},
        }
