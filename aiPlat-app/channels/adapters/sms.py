"""
SMS Channel Adapter (渠道广度延伸批次 14→18)

Parses SMS gateway webhook payloads (Twilio-style) into the unified
ChannelMessage format and formats responses for SMS providers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class SMSAdapter(ChannelAdapter):
    """SMS 适配器 (Twilio 风格 webhook)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # Twilio: {"From":"+15551234567","To":"+15559876543","Body":"hello","MessageSid":"SM..."}
        text = str(raw_data.get("Body", "") or raw_data.get("body", "") or "")
        from_num = str(raw_data.get("From", "") or raw_data.get("from", ""))
        to_num = str(raw_data.get("To", "") or raw_data.get("to", ""))
        msg_id = str(raw_data.get("MessageSid", "") or raw_data.get("message_sid", "") or raw_data.get("id", ""))
        return ChannelMessage(
            message_id=msg_id,
            channel=ChannelType.SMS,
            chat_id=f"{from_num}:{to_num}" if from_num and to_num else (from_num or to_num),
            user_id=from_num,
            text=text,
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "To": response.message_id,
            "Body": response.text,
        }
