"""
Email Channel Adapter (P1-A4)

Parses email messages (from a receiving handler) into the unified
ChannelMessage format. Reuses the existing email_notifier infrastructure
for the send path where available.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class EmailAdapter(ChannelAdapter):
    """Email 适配器 (SMTP/IMAP)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        return ChannelMessage(
            message_id=str(raw_data.get("message_id", "")),
            channel=ChannelType.EMAIL,
            chat_id=str(raw_data.get("from", "")),
            user_id=str(raw_data.get("from", "")),
            text=str(raw_data.get("body", "")),
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "to": response.message_id,
            "subject": "aiPlat 回复",
            "body": response.text,
        }
