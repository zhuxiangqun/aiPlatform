"""
IRC Channel Adapter (渠道广度延伸批次)

Parses IRC PRIVMSG payloads into the unified ChannelMessage
format and formats responses for IRC protocol.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class IRCAdapter(ChannelAdapter):
    """IRC 适配器 (PRIVMSG 协议)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # IRC 消息：{"prefix": "nick!user@host", "command": "PRIVMSG",
        #           "params": ["#channel", "message text"]}
        params = raw_data.get("params") or []
        channel = params[0] if params else ""
        text = params[1] if len(params) > 1 else ""
        prefix = str(raw_data.get("prefix", ""))
        nick = prefix.split("!")[0] if prefix else ""
        return ChannelMessage(
            message_id=str(raw_data.get("id", "") or f"{prefix}:{raw_data.get('command', '')}"),
            channel=ChannelType.IRC,
            chat_id=str(channel),
            user_id=str(nick),
            text=str(text),
            timestamp=datetime.now(),
            metadata={
                "command": raw_data.get("command", ""),
                "prefix": prefix,
                "raw": raw_data,
            },
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "command": "PRIVMSG",
            "message": response.text,
        }
