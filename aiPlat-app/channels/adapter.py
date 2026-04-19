"""
Channel Adapter - 消息通道适配器

统一消息格式，适配不同渠道（Telegram/Slack/WebChat）。
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
from dataclasses import dataclass
from enum import Enum
import uuid
from datetime import datetime


class ChannelType(str, Enum):
    TELEGRAM = "telegram"
    SLACK = "slack"
    WEBCHAT = "webchat"
    DISCORD = "discord"
    WECHAT = "wechat"


@dataclass
class ChannelMessage:
    """统一消息格式"""
    message_id: str
    channel: ChannelType
    chat_id: str
    user_id: str
    text: str
    timestamp: datetime
    metadata: Dict[str, Any]


@dataclass
class ChannelResponse:
    """统一响应格式"""
    message_id: str
    text: str
    markdown: Optional[str] = None
    buttons: Optional[list] = None


class ChannelAdapter(ABC):
    """通道适配器基类"""

    @abstractmethod
    def parse_message(self, raw_data: dict) -> ChannelMessage:
        """解析原始消息"""
        pass

    @abstractmethod
    def format_response(self, response: ChannelResponse) -> dict:
        """格式化响应"""
        pass


class TelegramAdapter(ChannelAdapter):
    """Telegram 适配器"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        message = raw_data.get("message", {})
        chat = message.get("chat", {})

        return ChannelMessage(
            message_id=str(message.get("message_id", "")),
            channel=ChannelType.TELEGRAM,
            chat_id=str(chat.get("id", "")),
            user_id=str(message.get("from", {}).get("id", "")),
            text=message.get("text", ""),
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "method": "sendMessage",
            "chat_id": response.message_id,
            "text": response.text,
            "parse_mode": "Markdown",
        }


class SlackAdapter(ChannelAdapter):
    """Slack 适配器"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        event = raw_data.get("event", {})

        return ChannelMessage(
            message_id=raw_data.get("event_id", ""),
            channel=ChannelType.SLACK,
            chat_id=event.get("channel", ""),
            user_id=event.get("user", ""),
            text=event.get("text", ""),
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "channel": response.message_id,
            "text": response.text,
        }


class WebChatAdapter(ChannelAdapter):
    """WebChat 适配器"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        return ChannelMessage(
            message_id=raw_data.get("message_id", str(uuid.uuid4())),
            channel=ChannelType.WEBCHAT,
            chat_id=raw_data.get("session_id", "default"),
            user_id=raw_data.get("user_id", "anonymous"),
            text=raw_data.get("text", ""),
            timestamp=datetime.now(),
            metadata=raw_data,
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "message_id": response.message_id,
            "text": response.text,
            "markdown": response.markdown,
            "buttons": response.buttons,
        }


class ChannelDispatcher:
    """通道调度器"""

    def __init__(self):
        self._adapters: Dict[ChannelType, ChannelAdapter] = {
            ChannelType.TELEGRAM: TelegramAdapter(),
            ChannelType.SLACK: SlackAdapter(),
            ChannelType.WEBCHAT: WebChatAdapter(),
        }

    def register_adapter(self, channel: ChannelType, adapter: ChannelAdapter) -> None:
        self._adapters[channel] = adapter

    def get_adapter(self, channel: ChannelType) -> ChannelAdapter:
        return self._adapters.get(channel, WebChatAdapter())

    def dispatch(self, channel: ChannelType, raw_data: dict) -> ChannelMessage:
        adapter = self.get_adapter(channel)
        return adapter.parse_message(raw_data)

    def reply(self, channel: ChannelType, message_id: str, text: str) -> dict:
        adapter = self.get_adapter(channel)
        response = ChannelResponse(message_id=message_id, text=text)
        return adapter.format_response(response)


channel_dispatcher = ChannelDispatcher()
channel_adapter = channel_dispatcher