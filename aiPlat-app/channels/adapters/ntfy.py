"""
ntfy Channel Adapter (渠道广度延伸批次)

Parses ntfy.sh publish payloads into the unified ChannelMessage
format and formats responses for the ntfy.sh API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class NtfyAdapter(ChannelAdapter):
    """ntfy.sh 适配器 (发布/订阅推送)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # ntfy publish 事件：{"id": "...", "topic": "...", "message": "...", "title": "..."}
        text = str(raw_data.get("message", ""))
        title = str(raw_data.get("title", ""))
        if title:
            text = f"{title}: {text}" if text else title
        return ChannelMessage(
            message_id=str(raw_data.get("id", "")),
            channel=ChannelType.NTFY,
            chat_id=str(raw_data.get("topic", "")),
            user_id=str(raw_data.get("topic", "")),
            text=text,
            timestamp=datetime.now(),
            metadata={
                "title": raw_data.get("title", ""),
                "tags": raw_data.get("tags") or [],
                "priority": raw_data.get("priority", 3),
                "raw": raw_data,
            },
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "topic": response.message_id,
            "message": response.text,
        }
