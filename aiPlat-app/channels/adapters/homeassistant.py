"""
Home Assistant Channel Adapter (渠道广度延伸批次)

Parses Home Assistant event payloads into the unified ChannelMessage
format and formats responses for the Home Assistant API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class HomeAssistantAdapter(ChannelAdapter):
    """Home Assistant 适配器 (REST API / WebSocket)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        event = raw_data.get("event") or raw_data
        data = event.get("data") or {}
        # HA 事件：event_type=call_service / state_changed 等
        text = str(data.get("message", "") or raw_data.get("message", ""))
        if not text and event.get("event_type") == "state_changed":
            text = str(data.get("entity_id", ""))
        return ChannelMessage(
            message_id=str(event.get("id", "") or raw_data.get("id", "")),
            channel=ChannelType.HOMEASSISTANT,
            chat_id=str(data.get("entity_id", "") or raw_data.get("origin", "")),
            user_id=str(data.get("user_id", "") or "ha"),
            text=text,
            timestamp=datetime.now(),
            metadata={
                "event_type": event.get("event_type", ""),
                "origin": raw_data.get("origin", ""),
                "raw": raw_data,
            },
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "message": response.text,
            "type": "notify",
        }
