from abc import ABC, abstractmethod
from typing import Any
from .schemas import PoolStats


class ConnectionPool(ABC):
    @abstractmethod
    async def acquire(self) -> Any:
        pass

    @abstractmethod
    async def release(self, conn: Any) -> None:
        pass

    @abstractmethod
    def get_stats(self) -> PoolStats:
        pass

    @abstractmethod
    async def resize(self, min_size: int, max_size: int) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass
