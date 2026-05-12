"""
Knowledge Retriever Module

Provides knowledge retrieval capabilities.
Phase 9: Unified embedder (HashEmbedder, InfraEmbedder), SqliteRetriever.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import hashlib
import math
import os

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
        pass

    @abstractmethod
    async def get_by_id(self, entry_id: str) -> Optional[KnowledgeEntry]:
        pass

    @abstractmethod
    async def get_similar(
        self,
        entry: KnowledgeEntry,
        limit: int = 10,
    ) -> List[KnowledgeResult]:
        pass

    @abstractmethod
    async def add(self, entry: KnowledgeEntry) -> None:
        pass

    @abstractmethod
    async def add_batch(self, entries: List[KnowledgeEntry]) -> None:
        pass


class IEmbedder(ABC):
    """Embedder interface for vector embeddings"""

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        pass


class HashEmbedder(IEmbedder):
    """Production-grade hash embedder using SHA-256 n-gram hashing."""

    def __init__(self, dimension: int = 128):
        self._dimension = dimension
        self._cache: Dict[str, List[float]] = {}

    async def embed(self, text: str) -> List[float]:
        key = hashlib.sha256(text.encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        vec = self._hash(text)
        if len(self._cache) < 2048:
            self._cache[key] = vec
        return vec

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(t) for t in texts]

    def _hash(self, text: str) -> List[float]:
        text = (text or "").strip()
        if not text:
            return [0.0] * self._dimension
        vec = [0.0] * self._dimension
        data = text.encode("utf-8", errors="ignore")
        for i in range(max(1, len(data))):
            chunk = data[i : i + 3] if i + 3 <= len(data) else data[i:]
            h = hashlib.sha256(chunk).digest()
            idx = int.from_bytes(h[:4], "big") % self._dimension
            sign = 1.0 if (h[4] % 2 == 0) else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class InfraEmbedder(IEmbedder):
    """Embedder backed by Infra LLM providers (OpenAI / DeepSeek)."""

    def __init__(self, provider_name: Optional[str] = None):
        self._provider_name = (provider_name or os.getenv("AIPLAT_EMBED_PROVIDER", "").lower().strip())
        self._provider = None
        self._cache: Dict[str, List[float]] = {}

    def _ensure_provider(self):
        if self._provider is not None:
            return self._provider
        try:
            if self._provider_name == "openai":
                from infra.llm.providers.openai import OpenAIProvider
                self._provider = OpenAIProvider()
            elif self._provider_name == "deepseek":
                from infra.llm.providers.deepseek import DeepSeekProvider
                self._provider = DeepSeekProvider()
        except Exception:
            pass
        return self._provider

    async def embed(self, text: str) -> List[float]:
        import hashlib as hl
        key = hl.sha256(text.encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        provider = self._ensure_provider()
        if provider is None:
            return HashEmbedder()._hash(text)
        try:
            result = await provider.embed([text])
            if result and hasattr(result, "data") and result.data:
                d = result.data[0]
                vec = d.embedding if hasattr(d, "embedding") else d
                if isinstance(vec, list) and len(vec) > 0:
                    if len(self._cache) < 2048:
                        self._cache[key] = vec
                    return vec
        except Exception:
            pass
        return HashEmbedder()._hash(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(t) for t in texts]


# Compatibility alias
SimpleEmbedder = HashEmbedder


class InMemoryRetriever(IRetriever):
    """In-memory knowledge retriever"""

    def __init__(self, embedder: Optional[IEmbedder] = None):
        self._embedder = embedder or HashEmbedder()
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