"""vector/base：向量库抽象接口。"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from .schemas import Vector, SearchResult


class VectorStore(ABC):
    """向量存储抽象接口。"""

    @abstractmethod
    async def add(
        self, vectors: List[Vector], metadata: List[Dict] = None
    ) -> List[str]:
        """写入向量。

        Args:
            vectors: 向量列表。
            metadata: 可选元数据列表。
        """
        pass

    @abstractmethod
    async def search(
        self, query_vector: List[float], top_k: int = 10, filter: Dict = None
    ) -> List[SearchResult]:
        """相似度检索。

        Args:
            query_vector: 查询向量。
            top_k: 返回条数上限。
            filter: 可选过滤条件。
        """
        pass

    @abstractmethod
    async def delete(self, ids: List[str]) -> bool:
        """按 ID 删除。

        Args:
            ids: 向量 ID 列表。
        """
        pass

    @abstractmethod
    async def get(self, id: str) -> Optional[Vector]:
        """按 ID 读取向量。

        Args:
            id: 向量 ID。
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """返回向量数量。"""
        pass

    @abstractmethod
    async def upsert(self, vectors: List[Vector]) -> List[str]:
        """插入或更新向量。

        Args:
            vectors: 向量列表。
        """
        pass

    @abstractmethod
    async def create_index(self, index_type: str, params: Dict) -> None:
        """创建索引。

        Args:
            index_type: 索引类型。
            params: 索引参数。
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭存储连接。"""
        pass
