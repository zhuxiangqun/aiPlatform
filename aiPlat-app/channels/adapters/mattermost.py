"""
Mattermost Channel Adapter (渠道广度延伸批次 10→14)

Parses Mattermost webhook/API payloads into the unified ChannelMessage
format and formats responses for Mattermost's incoming webhook API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class MattermostAdapter(ChannelAdapter):
    """Mattermost 适配器 (incoming/outgoing webhook)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # Mattermost webhook: {"text":"...","user_name":"...","channel_name":"...","user_id":"..."}
        text = str(raw_data.get("text", "") or "")
        # webhook 文本可能带 @mention 前缀噪音，保留原样（不做业务假设）
        channel = str(raw_data.get("channel_name", "") or raw_data.get("channel_id", ""))
        user = str(raw_data.get("user_id", "") or raw_data.get("user_name", ""))
        return ChannelMessage(
            message_id=str(raw_data.get("id", "") or f"mm-{len(text)}-{int(datetime.now().timestamp())}"),
            channel=ChannelType.MATTERMOST,
            chat_id=channel,
            user_id=user,
            text=text,
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "channel": response.message_id,
            "text": response.text,
        }
