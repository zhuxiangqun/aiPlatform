"""
Long-term Memory - 长期记忆
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import MemoryBase, MemoryEntry, MemoryScope, MemoryType


class LongTermMemory(MemoryBase):
    """长期记忆 - 持久化存储、语义检索"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.max_size = self.config.get("max_size", 10000)
        self.ttl = self.config.get("ttl", 86400 * 30)   # 30天
        self._storage: Dict[str, MemoryEntry] = {}
        self._index: Dict[str, set] = {}                 # 简单索引
        self._lock = asyncio.Lock()
    
    async def store(self, entry: MemoryEntry) -> str:
        """存储长期记忆"""
        async with self._lock:
            entry.id = entry.id or str(uuid.uuid4())
            if entry.expires_at is None:
                entry.expires_at = datetime.now().timestamp() + self.ttl
            
            self._storage[entry.id] = entry
            
            # 更新索引
            keywords = self._extract_keywords(entry.content)
            for keyword in keywords:
                if keyword not in self._index:
                    self._index[keyword] = set()
                self._index[keyword].add(entry.id)
            
            return entry.id
    
    async def retrieve(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """检索长期记忆（基于关键词匹配）"""
        async with self._lock:
            query_keywords = self._extract_keywords(query)
            if not query_keywords:
                # 无关键词，返回最近的
                sorted_entries = sorted(
                    self._storage.values(),
                    key=lambda e: e.timestamp,
                    reverse=True
                )
                return sorted_entries[:limit]
            
            # 计算相关性分数
            scores: Dict[str, float] = {}
            for keyword in query_keywords:
                if keyword in self._index:
                    for entry_id in self._index[keyword]:
                        scores[entry_id] = scores.get(entry_id, 0) + 1
            
            # 排序并返回
            sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
            return [
                self._storage[entry_id] 
                for entry_id in sorted_ids[:limit]
                if entry_id in self._storage
            ]
    
    async def retrieve_by_type(self, memory_type: MemoryType, limit: int = 10) -> List[MemoryEntry]:
        """按类型检索"""
        async with self._lock:
            entries = [
                e for e in self._storage.values()
                if e.memory_type == memory_type and not e.is_expired()
            ]
            return sorted(entries, key=lambda e: e.importance, reverse=True)[:limit]
    
    async def delete(self, entry_id: str) -> bool:
        """删除记忆"""
        async with self._lock:
            if entry_id in self._storage:
                entry = self._storage[entry_id]
                
                # 清理索引
                keywords = self._extract_keywords(entry.content)
                for keyword in keywords:
                    if keyword in self._index:
                        self._index[keyword].discard(entry_id)
                
                del self._storage[entry_id]
                return True
            return False
    
    async def clear(self, scope: MemoryScope = MemoryScope.SESSION) -> int:
        """清除长期记忆"""
        async with self._lock:
            count = len(self._storage)
            
            if scope == MemoryScope.GLOBAL:
                self._storage.clear()
                self._index.clear()
            else:
                # 保留语义记忆，只清除会话级
                to_delete = [
                    eid for eid, e in self._storage.items()
                    if e.metadata.get("scope") == scope.value
                ]
                for eid in to_delete:
                    await self.delete(eid)
            
            return count
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        async with self._lock:
            by_type = {}
            for entry in self._storage.values():
                type_name = entry.memory_type.value
                by_type[type_name] = by_type.get(type_name, 0) + 1
            
            return {
                "type": "LongTermMemory",
                "total_entries": len(self._storage),
                "max_size": self.max_size,
                "by_type": by_type
            }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（简单实现）"""
        words = text.lower().split()
        # 过滤停用词
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "of", "in", "on", "at", "to", "for"}
        return [w for w in words if w not in stopwords and len(w) > 2]


class SemanticMemory(LongTermMemory):
    """语义记忆 - 基于向量相似度的记忆"""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config.setdefault("max_size", 5000)
        config.setdefault("ttl", 86400 * 90)  # 90天
        super().__init__(config)
        self._embeddings: Dict[str, List[float]] = {}
    
    async def store_with_embedding(self, content: str, embedding: List[float], 
                                   memory_type: MemoryType = MemoryType.SEMANTIC,
                                   metadata: Dict[str, Any] = None) -> str:
        """存储带嵌入向量的记忆"""
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
            embeddings=embedding,
            importance=0.7
        )
        entry_id = await self.store(entry)
        self._embeddings[entry_id] = embedding
        return entry_id
    
    async def retrieve_similar(self, query_embedding: List[float], 
                              limit: int = 5, threshold: float = 0.8) -> List[MemoryEntry]:
        """基于向量相似度检索"""
        async with self._lock:
            results = []
            
            for entry_id, embedding in self._embeddings.items():
                if entry_id not in self._storage:
                    continue
                
                similarity = self._cosine_similarity(query_embedding, embedding)
                if similarity >= threshold:
                    entry = self._storage[entry_id]
                    entry.metadata["similarity"] = similarity
                    results.append(entry)
            
            return sorted(results, key=lambda e: e.metadata.get("similarity", 0), reverse=True)[:limit]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = sum(x * x for x in a) ** 0.5
        magnitude_b = sum(x * x for x in b) ** 0.5
        
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        
        return dot_product / (magnitude_a * magnitude_b)