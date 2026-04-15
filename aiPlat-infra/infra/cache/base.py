from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class CacheClient(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 0) -> bool:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    async def clear(self) -> None:
        pass

    @abstractmethod
    async def keys(self, pattern: str) -> List[str]:
        pass

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> bool:
        pass

    @abstractmethod
    async def ttl(self, key: str) -> int:
        pass


class CacheManager(ABC):
    @abstractmethod
    async def get_or_set(self, key: str, factory: Any, ttl: int) -> Any:
        pass

    @abstractmethod
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def set_many(self, items: Dict[str, Any], ttl: int) -> None:
        pass

    @abstractmethod
    async def delete_many(self, keys: List[str]) -> None:
        pass

    @abstractmethod
    async def get_stats(self) -> "CacheStats":
        pass
