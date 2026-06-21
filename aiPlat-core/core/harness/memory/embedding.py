"""
EmbeddingProvider — unified text embedding interface.

Supports multiple backends via configuration:
- transform (default): uses sentence-transformers for local embeddings
- api: uses OpenAI-compatible embedding API
- cache: caches embeddings in memory for repeated texts

Usage:
    provider = EmbeddingProvider()
    vectors = await provider.embed(["text1", "text2"])
    similarity = provider.cosine_similarity(vec1, vec2)
"""

from __future__ import annotations

import os
import math
from typing import Any, Dict, List, Optional

import asyncio


class EmbeddingProvider:
    def __init__(self, *, backend: str = "", model_name: str = "", cache_size: int = 1000):
        self._backend = backend or os.getenv("AIPLAT_EMBEDDING_BACKEND", "transform")
        if model_name:
            self._model_name = model_name
        else:
            try:
                from core.harness.infrastructure.base_model_adapter import resolve_model_name, _MODEL_DEFAULTS
                self._model_name = resolve_model_name("embedding")
            except Exception:
                from core.harness.infrastructure.base_model_adapter import _MODEL_DEFAULTS
                self._model_name = _MODEL_DEFAULTS.get("embedding", "paraphrase-multilingual-MiniLM-L12-v2")
        self._model: Any = None
        self._cache: Dict[str, List[float]] = {}
        self._cache_size = cache_size
        self._api_key = os.getenv("AIPLAT_EMBEDDING_API_KEY", "")
        self._api_url = os.getenv("AIPLAT_EMBEDDING_API_URL", "")

    async def embed(self, texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        to_embed: List[str] = []
        to_embed_indices: List[int] = []

        for i, text in enumerate(texts):
            key = f"{self._model_name}:{text[:200]}"
            cached = self._cache.get(key)
            if cached is not None:
                results.append(cached)
            else:
                results.append([])  # placeholder
                to_embed.append(text)
                to_embed_indices.append(i)

        if not to_embed:
            return results

        vectors = await self._embed_batch(to_embed)

        for idx, vec in zip(to_embed_indices, vectors):
            results[idx] = vec
            key = f"{self._model_name}:{to_embed[to_embed_indices.index(idx)][:200]}"
            if len(self._cache) < self._cache_size:
                self._cache[key] = vec

        return results

    async def embed_single(self, text: str) -> List[float]:
        results = await self.embed([text])
        return results[0] if results else []

    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self._backend == "transform":
            return await self._embed_transform(texts)
        elif self._backend == "api":
            return await self._embed_api(texts)
        elif self._backend == "infra":
            return await self._embed_infra(texts)
        elif self._backend == "simple":
            return self._embed_simple(texts)
        else:
            return await self._embed_transform(texts)

    async def _embed_transform(self, texts: List[str]) -> List[List[float]]:
        try:
            # Prefer InfraEmbeddingAdapter
            from core.harness.infrastructure.base_model_adapter import create_adapter
            if self._model is None:
                self._model = create_adapter("embedding")
            loop = asyncio.get_running_loop()
            embeddings = await loop.run_in_executor(
                None, lambda: self._model.embed_batch_sync(texts)
            )
            return [[float(v) for v in emb] for emb in embeddings]
        except Exception:
            pass
        try:
            from sentence_transformers import SentenceTransformer
            if self._model is None:
                self._model = SentenceTransformer(self._model_name, local_files_only=True)
            loop = asyncio.get_running_loop()
            embeddings = await loop.run_in_executor(
                None, lambda: self._model.encode(texts, show_progress_bar=False).tolist()
            )
            return [[float(v) for v in emb] for emb in embeddings]
        except ImportError:
            return self._embed_simple(texts)
        except Exception:
            return self._embed_simple(texts)

    async def _embed_api(self, texts: List[str]) -> List[List[float]]:
        if not self._api_url:
            return self._embed_simple(texts)
        import aiohttp
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {"input": texts, "model": self._model_name}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._api_url.rstrip('/')}/embeddings",
                    json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [d["embedding"] for d in data.get("data", [])]
        except Exception:
            pass
        return self._embed_simple(texts)

    async def _embed_infra(self, texts: List[str]) -> List[List[float]]:
        """Use infra layer embedding (via infra_bridge)."""
        try:
            from core.harness.infrastructure.infra_bridge import get_infra_embedding
            results = []
            for text in texts:
                vec = await get_infra_embedding(text)
                if vec:
                    results.append(vec)
                else:
                    results.append(self._embed_simple([text])[0])
            return results
        except Exception:
            return self._embed_simple(texts)

    def _embed_simple(self, texts: List[str]) -> List[List[float]]:
        import hashlib
        vectors = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h[:64]]
            vec += [0.0] * (64 - len(vec))
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def top_k_similar(
        query_vec: List[float],
        candidates: List[tuple],
        k: int = 5,
    ) -> List[tuple]:
        scored = []
        for item in candidates:
            sim = EmbeddingProvider.cosine_similarity(query_vec, item[1])
            scored.append((item[0], sim))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]


_embedding_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = EmbeddingProvider()
    return _embedding_provider


__all__ = [
    "EmbeddingProvider",
    "get_embedding_provider",
]
