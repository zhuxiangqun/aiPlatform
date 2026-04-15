"""
Knowledge Retriever Module

Provides knowledge retrieval capabilities.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from .types import (
    KnowledgeEntry,
    KnowledgeQuery,
    KnowledgeResult,
    KnowledgeType,
    KnowledgeSource,
    KnowledgeMetadata,
)


class IRetriever(ABC):
    """Knowledge retriever interface"""
    
    @abstractmethod
    async def retrieve(self, query: KnowledgeQuery) -> List[KnowledgeResult]:
        """Retrieve knowledge entries matching the query"""
        pass
    
    @abstractmethod
    async def get_by_id(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """Get a knowledge entry by ID"""
        pass
    
    @abstractmethod
    async def get_similar(
        self,
        entry: KnowledgeEntry,
        limit: int = 10,
    ) -> List[KnowledgeResult]:
        """Get similar knowledge entries"""
        pass


class IEmbedder(ABC):
    """Embedder interface for vector embeddings"""
    
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Generate embedding for text"""
        pass
    
    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        pass


class SimpleEmbedder(IEmbedder):
    """Simple embedder using hash-based vectors"""
    
    def __init__(self, dimension: int = 128):
        self._dimension = dimension
    
    async def embed(self, text: str) -> List[float]:
        hash_value = hash(text)
        embedding = [0.0] * self._dimension
        for i in range(self._dimension):
            embedding[i] = ((hash_value >> (i % 32)) & 1) * 2 - 1
        return embedding
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(t) for t in texts]


class InMemoryRetriever(IRetriever):
    """In-memory knowledge retriever"""
    
    def __init__(self, embedder: Optional[IEmbedder] = None):
        self._embedder = embedder or SimpleEmbedder()
        self._entries: Dict[str, KnowledgeEntry] = {}
        self._embeddings: Dict[str, List[float]] = {}
    
    async def add(self, entry: KnowledgeEntry):
        self._entries[entry.id] = entry
        if entry.embedding:
            self._embeddings[entry.id] = entry.embedding
        else:
            self._embeddings[entry.id] = await self._embedder.embed(entry.content)
    
    async def add_batch(self, entries: List[KnowledgeEntry]):
        for entry in entries:
            await self.add(entry)
    
    async def remove(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._embeddings.pop(entry_id, None)
            return True
        return False
    
    async def retrieve(self, query: KnowledgeQuery) -> List[KnowledgeResult]:
        results: List[Tuple[float, KnowledgeEntry]] = []
        
        query_embedding = query.query_embedding
        if query_embedding is None:
            query_embedding = await self._embedder.embed(query.query)
        
        for entry_id, entry in self._entries.items():
            if query.types and entry.type not in query.types:
                continue
            if query.sources and entry.metadata.source not in query.sources:
                continue
            if query.tags and not all(t in entry.metadata.tags for t in query.tags):
                continue
            if entry.metadata.confidence < query.min_confidence:
                continue
            
            embedding = self._embeddings.get(entry_id)
            if embedding:
                score = self._cosine_similarity(query_embedding, embedding)
                if score >= query.min_relevance:
                    results.append((score, entry))
        
        results.sort(key=lambda x: x[0], reverse=True)
        
        return [
            KnowledgeResult(entry=entry, score=score)
            for score, entry in results[: query.limit]
        ]
    
    async def get_by_id(self, entry_id: str) -> Optional[KnowledgeEntry]:
        return self._entries.get(entry_id)
    
    async def get_similar(
        self,
        entry: KnowledgeEntry,
        limit: int = 10,
    ) -> List[KnowledgeResult]:
        if entry.id not in self._embeddings:
            return []
        
        query = KnowledgeQuery(
            query=entry.content,
            query_embedding=self._embeddings[entry.id],
            limit=limit + 1,
        )
        
        results = await self.retrieve(query)
        return [r for r in results if r.entry.id != entry.id][:limit]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x ** 2 for x in a) ** 0.5
        norm_b = sum(x ** 2 for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    
    def count(self) -> int:
        return len(self._entries)
    
    def clear(self):
        self._entries.clear()
        self._embeddings.clear()


class KnowledgeRetriever:
    """High-level knowledge retriever"""
    
    def __init__(self, retriever: Optional[IRetriever] = None):
        self._retriever = retriever or InMemoryRetriever()
    
    async def search(self, query: str, limit: int = 10) -> List[KnowledgeResult]:
        knowledge_query = KnowledgeQuery(query=query, limit=limit)
        return await self._retriever.retrieve(knowledge_query)
    
    async def search_by_type(
        self,
        query: str,
        knowledge_type: KnowledgeType,
        limit: int = 10,
    ) -> List[KnowledgeResult]:
        knowledge_query = KnowledgeQuery(
            query=query,
            types=[knowledge_type],
            limit=limit,
        )
        return await self._retriever.retrieve(knowledge_query)
    
    async def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        return await self._retriever.get_by_id(entry_id)
    
    async def find_similar(
        self,
        entry_id: str,
        limit: int = 10,
    ) -> List[KnowledgeResult]:
        entry = await self._retriever.get_by_id(entry_id)
        if not entry:
            return []
        return await self._retriever.get_similar(entry, limit)
    
    async def add_knowledge(
        self,
        content: str,
        title: Optional[str] = None,
        knowledge_type: KnowledgeType = KnowledgeType.DOCUMENT,
        source: KnowledgeSource = KnowledgeSource.USER,
        tags: Optional[List[str]] = None,
    ) -> KnowledgeEntry:
        if isinstance(self._retriever, InMemoryRetriever):
            import uuid
            entry = KnowledgeEntry(
                id=str(uuid.uuid4()),
                type=knowledge_type,
                content=content,
                title=title,
                metadata=KnowledgeMetadata(
                    source=source,
                    tags=tags or [],
                ),
            )
            await self._retriever.add(entry)
            return entry
        raise NotImplementedError("Retriever does not support adding entries")


def create_retriever(
    embedder: Optional[IEmbedder] = None,
) -> KnowledgeRetriever:
    return KnowledgeRetriever(InMemoryRetriever(embedder))


__all__ = [
    "IRetriever",
    "IEmbedder",
    "SimpleEmbedder",
    "InMemoryRetriever",
    "KnowledgeRetriever",
    "create_retriever",
]