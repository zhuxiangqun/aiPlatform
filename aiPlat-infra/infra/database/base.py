from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager


class DatabaseClient(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def execute(self, query: str, params: Dict = None) -> List[Dict]:
        pass

    @abstractmethod
    async def execute_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        pass

    @abstractmethod
    async def execute_many(self, query: str, params_list: List[Dict]) -> List[Any]:
        pass

    @asynccontextmanager
    @abstractmethod
    async def transaction(self):
        pass

    @abstractmethod
    async def begin(self) -> None:
        pass

    @abstractmethod
    async def commit(self) -> None:
        pass

    @abstractmethod
    async def rollback(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass


class ConnectionPool(ABC):
    @abstractmethod
    async def acquire(self) -> Any:
        pass

    @abstractmethod
    async def release(self, conn: Any) -> None:
        pass

    @abstractmethod
    def get_stats(self) -> "PoolStats":
        pass

    @abstractmethod
    async def resize(self, min_size: int, max_size: int) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass
