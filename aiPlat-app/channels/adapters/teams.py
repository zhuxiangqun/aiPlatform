"""
Microsoft Teams Channel Adapter (渠道广度延伸批次)

Parses Teams activity payloads into the unified ChannelMessage format
and formats responses for Teams Bot Framework.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class TeamsAdapter(ChannelAdapter):
    """Microsoft Teams 适配器 (Bot Framework)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        text = str(raw_data.get("text", ""))
        return ChannelMessage(
            message_id=str(raw_data.get("id", "")),
            channel=ChannelType.TEAMS,
            chat_id=str((raw_data.get("conversation") or {}).get("id", "")),
            user_id=str((raw_data.get("from") or {}).get("id", "")),
            text=text,
            timestamp=datetime.now(),
            metadata={
                "service_url": raw_data.get("serviceUrl", ""),
                "channel_id": raw_data.get("channelId", ""),
                "conversation_type": (raw_data.get("conversation") or {}).get("conversationType", ""),
                "raw": raw_data,
            },
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "type": "message",
            "text": response.text,
        }
