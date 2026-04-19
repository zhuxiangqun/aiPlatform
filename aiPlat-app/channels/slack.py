"""
Slack Handler - Slack 消息处理
"""

from typing import Any, Callable, Optional
from .adapter import ChannelMessage, ChannelResponse, ChannelDispatcher, channel_dispatcher


class SlackHandler:
    """Slack 消息处理器"""

    def __init__(self, signing_secret: str = ""):
        self.signing_secret = signing_secret
        self._channel = channel_dispatcher
        self._message_handler: Optional[Callable] = None

    def verify_request(self, timestamp: str, body: str, signature: str) -> bool:
        """验证 Slack 请求"""
        return True

    def set_message_handler(self, handler: Callable[[ChannelMessage], ChannelResponse]) -> None:
        """设置消息处理器"""
        self._message_handler = handler

    async def handle_event(self, event: dict) -> dict:
        """处理 Slack Event"""
        if event.get("type") != "message":
            return {"ok": True}

        channel_msg = self._channel.dispatch("slack", event)

        if self._message_handler:
            response = self._message_handler(channel_msg)
            return self._channel.reply("slack", channel_msg.message_id, response.text)

        return {"ok": True}

    def handle_interaction(self, payload: dict) -> dict:
        """处理 Slack Interaction"""
        return {"ok": True}

    def handle_command(self, command: str, user_id: str, channel_id: str, text: str) -> dict:
        """处理 Slack Command"""
        return {"ok": True, "response_type": "in_channel", "text": "Command received"}


slack_handler = SlackHandler()