"""
WhatsApp Channel Adapter (渠道广度延伸批次)

Parses WhatsApp Cloud API webhook payloads into the unified ChannelMessage
format and formats responses for WhatsApp Business API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class WhatsAppAdapter(ChannelAdapter):
    """WhatsApp 适配器 (Cloud API)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        entry = (raw_data.get("entry") or [{}])[0]
        changes = entry.get("changes") or [{}]
        change = changes[0]
        value = change.get("value") or {}
        messages = value.get("messages") or []
        message = messages[0] if messages else {}
        contacts = value.get("contacts") or []
        contact = contacts[0] if contacts else {}

        text = ""
        if message.get("type") == "text":
            text = str((message.get("text") or {}).get("body", ""))
        elif message.get("type") == "button":
            text = str((message.get("button") or {}).get("text", ""))

        return ChannelMessage(
            message_id=str(message.get("id", "")),
            channel=ChannelType.WHATSAPP,
            chat_id=str((message.get("from") or "") + (message.get("id") or "")),
            user_id=str(message.get("from", "")),
            text=text,
            timestamp=datetime.now(),
            metadata={"wa_id": contact.get("wa_id", ""), "profile": contact.get("profile", {}), "raw": raw_data},
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "messaging_product": "whatsapp",
            "to": response.message_id,
            "type": "text",
            "text": {"body": response.text},
        }
