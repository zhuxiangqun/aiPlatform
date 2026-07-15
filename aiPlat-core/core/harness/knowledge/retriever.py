from core.utils.math_utils import cosine_similarity
"""
Knowledge Retriever Module

Production retrieval: KnowledgeRetriever + InMemoryRetriever + VectorStoreRetriever
via factory functions create_retriever() (7 callers) and create_vector_retriever() (4 callers).
IRetriever/IEmbedder are interface contracts for embedder backends.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import logging
import uuid

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
    """Hash embedder — delegates to embedder.hash_embed().

    Used as fallback by create_default_embedder() when no semantic backend is available.
    For direct hash embedding, prefer embedder.hash_embed() which has 4 independent callers.
    """

    def __init__(self, dimension: int = 128):
        self._dimension = dimension

    async def embed(self, text: str) -> List[float]:
        from .embedder import hash_embed as _hash_embed
        return _hash_embed(text, dim=self._dimension)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        from .embedder import hash_embed as _hash_embed
        return [_hash_embed(t, dim=self._dimension) for t in texts]


# Compatibility alias — 2 callers (embedder.py create_default_embedder + tests)
SimpleEmbedder = HashEmbedder


class InMemoryRetriever(IRetriever):
    """In-memory knowledge retriever"""

    def __init__(self, embedder: Optional[IEmbedder] = None):
        if embedder is not None:
            self._embedder = embedder
        else:
            from .embedder import create_default_embedder
            self._embedder = create_default_embedder()
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

    def __init__(self, retriever: Optional[IRetriever] = None, retrieval_strategy: str = "hybrid", rerank_enabled: bool = False, rerank_method: str = "bm25", rerank_top_k: int = 5, quality_gate_enabled: bool = False, quality_threshold: float = 0.3, hyde_enabled: bool = False, hyde_model: Any = None, adaptive_routing: bool = False):
        self._retriever = retriever or InMemoryRetriever()
        self._retrieval_strategy = retrieval_strategy  # "hybrid" | "vector_only" | "keyword_only"
        self._rerank_enabled = rerank_enabled
        self._rerank_method = rerank_method    # "bm25" | "multi_factor"
        self._rerank_top_k = rerank_top_k
        self._quality_gate_enabled = quality_gate_enabled
        self._quality_threshold = quality_threshold
        self._hyde_enabled = hyde_enabled
        self._hyde_model = hyde_model
        self._adaptive_routing = adaptive_routing

    async def search(self, query: str, limit: int = 10) -> List[KnowledgeResult]:
        # Adaptive routing: adjust strategy based on query complexity (P1)
        effective_strategy = self._retrieval_strategy
        effective_rerank = self._rerank_enabled
        effective_qgate = self._quality_gate_enabled
        if self._adaptive_routing:
            from .complexity_router import classify_complexity, route_to_strategy
            route, reason = classify_complexity(query)
            if route == "direct":
                return []
            cfg = route_to_strategy(route)
            effective_strategy = cfg["retrieval_strategy"]
            effective_rerank = cfg["rerank_enabled"]
            effective_qgate = cfg["quality_gate_enabled"]

        # HyDE: generate hypothetical answer for embedding (P1)
        search_query = query
        if self._hyde_enabled and self._hyde_model:
            from .hyde_expander import hyde_expand
            hyde_text = await hyde_expand(query, self._hyde_model)
            if hyde_text:
                search_query = hyde_text

        knowledge_query = KnowledgeQuery(query=search_query, limit=limit)
        results = await self._retriever.retrieve(knowledge_query)


        if effective_strategy == "keyword_only":
            chunks = [r.content for r in results] if results else []
            if chunks:
                from .hybrid_retriever import keyword_search
                scored = keyword_search(query, chunks, top_k=limit)
                filtered = [results[i] for i, _ in scored if i < len(results)]
                return filtered[:limit] if filtered else results[:limit]
            return results[:limit]

        if effective_strategy == "hybrid" and len(results) > 0:
            chunks = [r.content for r in results]
            try:
                from .hybrid_retriever import keyword_search, rrf_fusion
                vec_ranked = [(i, r) for i, r in enumerate(results)]
                kw_ranked = [(i, results[i]) for i, s in keyword_search(search_query, chunks, top_k=20)]
                merged = rrf_fusion(vec_ranked, kw_ranked, k=60, top_n=limit)
                return merged[:limit] if merged else results[:limit]
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        # Re-rank: select top_k most relevant chunks (reduces token waste and noise)
        if effective_rerank and len(results) > self._rerank_top_k:
            try:
                from . import reranker
                chunks = [r.content for r in results]
                if self._rerank_method == "multi_factor":
                    scored = reranker.rerank_by_multi_factor(search_query, chunks, top_k=self._rerank_top_k)
                else:
                    scored = reranker.rerank_by_relevance(search_query, chunks, top_k=self._rerank_top_k)
                results = [results[i] for i, _ in scored if i < len(results)]
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        # CRAG quality gate: if retrieved chunks are low quality, flag for web search fallback
        if effective_qgate and results:
            try:
                from .retrieval_quality_gate import check_quality
                chunks = [r.content for r in results]
                gate = check_quality(chunks, query, threshold=self._quality_threshold)
                for r in results:
                    r.metadata = dict(getattr(r, 'metadata', None) or {})
                    r.metadata["_quality_gate"] = gate["action"]
                    r.metadata["_avg_relevance"] = gate["avg_score"]
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        # Provenance stale filter — exclude results from known-stale sources
        if results:
            try:
                from .provenance import get_provenance_tracker
                tracker = get_provenance_tracker()
                stale_ids = tracker.get_stale_source_ids()
                if stale_ids:
                    before = len(results)
                    results = [
                        r for r in results
                        if str(getattr(r, 'source_page', '') or getattr(r.entry, 'title', '')) not in stale_ids
                    ]
                    if len(results) < before:
                        import logging
                        logging.getLogger("aiplat.retrieval").info(
                            f"Provenance stale filter: {before - len(results)}/{before} results excluded"
                        )
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        return results[:limit]

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


def create_retriever(
    embedder: Optional[IEmbedder] = None,
) -> KnowledgeRetriever:
    """Create a KnowledgeRetriever with InMemoryRetriever backend."""
    return KnowledgeRetriever(InMemoryRetriever(embedder))


def create_vector_retriever(
    *, backend: str = "faiss", embedder: Optional[IEmbedder] = None,
) -> KnowledgeRetriever:
    """Create a KnowledgeRetriever backed by infra vector store (FAISS/Milvus/Chroma/Pinecone).
    
    Falls back to InMemoryRetriever if infra is unavailable.
    """
    try:
        retriever = VectorStoreRetriever(backend=backend, embedder=embedder)
        return KnowledgeRetriever(retriever)
    except Exception:
        return KnowledgeRetriever(InMemoryRetriever(embedder))


class VectorStoreRetriever(IRetriever):
    """Retriever backed by infra vector store (FAISS/Milvus/Chroma/Pinecone).
    
    Implements IRetriever using infra's VectorStore interface.
    Works alongside InMemoryRetriever but with persistent, indexed storage.
    """

    def __init__(self, *, backend: str = "faiss", embedder: Optional[IEmbedder] = None):
        from .embedder import create_default_embedder
        self._backend_name = backend
        self._embedder = embedder or create_default_embedder()
        self._client: Any = None
        self._initialized = False

    async def _ensure_client(self):
        if self._initialized:
            return
        from core.harness.infrastructure.infra_bridge import create_infra_vector_client
        self._client = create_infra_vector_client(self._backend_name)
        if self._client is None:
            self._client = None
            raise RuntimeError(
                f"Infra vector store '{self._backend_name}' not available. "
                "Ensure aiplat-infra is installed and configured."
            )
        self._initialized = True

    async def add(self, entry: KnowledgeEntry):
        await self._ensure_client()
        vec = entry.embedding or await self._embedder.embed(entry.content)
        import uuid
        vid = entry.id or str(uuid.uuid4())
        try:
            from infra.vector.schemas import Vector
        except ImportError:
            return
        vector = Vector(
            id=vid,
            values=vec,
            metadata={
                "type": entry.type.value if entry.type else "",
                "title": entry.title or "",
                "source": entry.metadata.source.value if entry.metadata and entry.metadata.source else "",
                "tags": ",".join(entry.metadata.tags) if entry.metadata and entry.metadata.tags else "",
            },
        )
        await self._client.add([vector])

    async def add_batch(self, entries: List[KnowledgeEntry]):
        for entry in entries:
            await self.add(entry)

    async def retrieve(self, query: KnowledgeQuery) -> List[KnowledgeResult]:
        await self._ensure_client()
        qvec = query.query_embedding or await self._embedder.embed(query.query)
        try:
            from infra.vector.schemas import Vector, SearchResult as InfraSearchResult
        except ImportError:
            return []
        filter_dict = {}
        if query.types:
            filter_dict["type"] = [t.value for t in query.types]
        if query.sources:
            filter_dict["source"] = [s.value for s in query.sources]
        if query.tags:
            filter_dict["tags"] = ",".join(query.tags)
        infra_results = await self._client.search(qvec, top_k=query.limit, filter=filter_dict if filter_dict else None)
        results = []
        for r in infra_results:
            if hasattr(r, 'score') and r.score >= query.min_relevance:
                entry = KnowledgeEntry(
                    id=r.id,
                    type=KnowledgeType.DOCUMENT,
                    content=r.metadata.get("title", "") if isinstance(r.metadata, dict) else "",
                    metadata=KnowledgeMetadata(
                        source=KnowledgeSource.SYSTEM,
                        tags=r.metadata.get("tags", "").split(",") if isinstance(r.metadata, dict) and r.metadata.get("tags") else [],
                    ),
                )
                results.append(KnowledgeResult(entry=entry, score=r.score))
        return results[:query.limit]

    async def get_by_id(self, entry_id: str) -> Optional[KnowledgeEntry]:
        await self._ensure_client()
        try:
            vec = await self._client.get(entry_id)
        except Exception:
            return None
        if vec is None:
            return None
        return KnowledgeEntry(
            id=entry_id,
            type=KnowledgeType.DOCUMENT,
            content="",
        )

    async def get_similar(
        self, entry: KnowledgeEntry, limit: int = 10,
    ) -> List[KnowledgeResult]:
        q = KnowledgeQuery(
            query=entry.content,
            query_embedding=entry.embedding,
            limit=limit + 1,
        )
        results = await self.retrieve(q)
        return [r for r in results if r.entry.id != entry.id][:limit]