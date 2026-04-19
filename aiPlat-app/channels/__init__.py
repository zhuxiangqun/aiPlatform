"""Channels Module - Message Gateway

消息通道负责多渠道接入能力的统一抽象。
"""

from .adapter import channel_adapter, ChannelAdapter
from .telegram import telegram_handler
from .slack import slack_handler

__all__ = ["channel_adapter", "ChannelAdapter", "telegram_handler", "slack_handler"]