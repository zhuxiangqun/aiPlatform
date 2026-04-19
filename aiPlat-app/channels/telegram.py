"""
Telegram Handler - Telegram 消息处理
"""

from typing import Any, Callable, Optional
import hashlib
import hmac
import time
from .adapter import ChannelMessage, ChannelResponse, ChannelDispatcher, channel_dispatcher


class TelegramHandler:
    """Telegram 消息处理器"""

    def __init__(self, bot_token: str = "", secret_token: str = ""):
        self.bot_token = bot_token
        self.secret_token = secret_token
        self._channel = channel_dispatcher
        self._message_handler: Optional[Callable] = None

    def verify_webhook(self, data: bytes, signature: str) -> bool:
        """验证 Webhook 请求"""
        if not self.secret_token:
            return True

        expected = hmac.new(
            self.secret_token.encode(),
            data,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    def set_message_handler(self, handler: Callable[[ChannelMessage], ChannelResponse]) -> None:
        """设置消息处理器"""
        self._message_handler = handler

    async def handle_update(self, update: dict) -> dict:
        """处理 Telegram Update"""
        message = update.get("message", {})
        if not message:
            return {"ok": True}

        channel_msg = self._channel.dispatch("telegram", update)

        if self._message_handler:
            response = self._message_handler(channel_msg)
            return self._channel.reply("telegram", channel_msg.message_id, response.text)

        return {"ok": True, "result": {"method": "sendMessage", "chat_id": channel_msg.chat_id, "text": "Received"}}

    def set_commands(self, commands: list[dict]) -> None:
        """设置命令列表"""
        pass


telegram_handler = TelegramHandler()