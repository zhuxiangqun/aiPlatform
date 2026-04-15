from abc import ABC, abstractmethod
from typing import Callable, Optional

from .schemas import Message, ConsumerConfig


class MessageClient(ABC):
    @abstractmethod
    async def publish(self, topic: str, message: bytes, **kwargs) -> None:
        pass

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], None],
        config: Optional[ConsumerConfig] = None,
    ) -> None:
        pass

    @abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        pass

    @abstractmethod
    async def ack(self, message_id: str) -> None:
        pass

    @abstractmethod
    async def nack(self, message_id: str) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass
