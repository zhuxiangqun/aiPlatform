from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from .schemas import Vector, SearchResult


class VectorStore(ABC):
    @abstractmethod
    async def add(
        self, vectors: List[Vector], metadata: List[Dict] = None
    ) -> List[str]:
        pass

    @abstractmethod
    async def search(
        self, query_vector: List[float], top_k: int = 10, filter: Dict = None
    ) -> List[SearchResult]:
        pass

    @abstractmethod
    async def delete(self, ids: List[str]) -> bool:
        pass

    @abstractmethod
    async def get(self, id: str) -> Optional[Vector]:
        pass

    @abstractmethod
    async def count(self) -> int:
        pass

    @abstractmethod
    async def upsert(self, vectors: List[Vector]) -> List[str]:
        pass

    @abstractmethod
    async def create_index(self, index_type: str, params: Dict) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass
