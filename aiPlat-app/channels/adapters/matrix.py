"""
Matrix Channel Adapter (渠道广度延伸批次 10→14)

Parses Matrix client-server API event payloads (rooms/{roomId}/event,
sync events) into the unified ChannelMessage format.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class MatrixAdapter(ChannelAdapter):
    """Matrix 适配器 (client-server API)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # Matrix event: {"type":"m.room.message","content":{"msgtype":"m.text","body":"..."},
        #   "sender":"@user:server","event_id":"$...","room_id":"!..."}
        content = raw_data.get("content") or {}
        event_type = raw_data.get("type", "")
        text = str(content.get("body", "") or "")
        if event_type != "m.room.message":
            text = f"[{event_type}] {text}"
        return ChannelMessage(
            message_id=str(raw_data.get("event_id", "")),
            channel=ChannelType.MATRIX,
            chat_id=str(raw_data.get("room_id", "")),
            user_id=str(raw_data.get("sender", "")),
            text=text,
            timestamp=datetime.now(),
            metadata={"msgtype": content.get("msgtype", ""), "raw": raw_data},
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "msgtype": "m.text",
            "body": response.text,
        }
