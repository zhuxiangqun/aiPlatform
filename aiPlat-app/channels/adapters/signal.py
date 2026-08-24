"""
Signal Channel Adapter (渠道广度延伸批次 10→14)

Parses Signal message payloads (from signal-cli json output / webhook)
into the unified ChannelMessage format and formats responses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class SignalAdapter(ChannelAdapter):
    """Signal 适配器 (signal-cli json / webhook)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # signal-cli receive 输出：{"envelope": {"source": "...", "sourceUuid": "...",
        #   "timestamp": ..., "dataMessage": {"message": "...", "timestamp": ...}}}
        envelope = raw_data.get("envelope") or raw_data
        data_msg = envelope.get("dataMessage") or {}
        text = str(data_msg.get("message", "") or "")
        source = str(envelope.get("source", "") or envelope.get("sourceUuid", ""))
        return ChannelMessage(
            message_id=str(envelope.get("timestamp", "") or data_msg.get("timestamp", "")),
            channel=ChannelType.SIGNAL,
            chat_id=source,
            user_id=source,
            text=text,
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "recipient": response.message_id,
            "message": response.text,
        }
