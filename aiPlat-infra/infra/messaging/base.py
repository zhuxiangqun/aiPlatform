"""messaging/base：消息客户端抽象接口。"""

from abc import ABC, abstractmethod
from typing import Callable, Optional

from .schemas import Message, ConsumerConfig


class MessageClient(ABC):
    """消息客户端抽象接口。"""

    @abstractmethod
    async def publish(self, topic: str, message: bytes, **kwargs) -> None:
        """发布消息。

        Args:
            topic: 主题。
            message: 消息字节。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], None],
        config: Optional[ConsumerConfig] = None,
    ) -> None:
        """订阅主题。

        Args:
            topic: 主题。
            handler: 消息处理器。
            config: 可选消费者配置。
        """
        pass

    @abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        """取消订阅。

        Args:
            topic: 主题。
        """
        pass

    @abstractmethod
    async def ack(self, message_id: str) -> None:
        """确认消息。

        Args:
            message_id: 消息 ID。
        """
        pass

    @abstractmethod
    async def nack(self, message_id: str) -> None:
        """否定确认消息。

        Args:
            message_id: 消息 ID。
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭客户端。"""
        pass
