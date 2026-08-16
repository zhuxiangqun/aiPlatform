"""
Discord Channel Adapter (P1-A4)

Parses Discord webhook/interaction payloads into the unified ChannelMessage
format and formats responses for Discord's API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class DiscordAdapter(ChannelAdapter):
    """Discord 适配器 (bot + webhook)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        message = raw_data.get("message", raw_data)
        author = message.get("author", {})
        channel = message.get("channel", {})

        return ChannelMessage(
            message_id=str(message.get("id", "")),
            channel=ChannelType.DISCORD,
            chat_id=str(channel.get("id", "")),
            user_id=str(author.get("id", "")),
            text=message.get("content", ""),
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
            "data": {"content": response.text},
        }
