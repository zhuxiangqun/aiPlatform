"""
Unified embedding provider — real semantic embedding with hash fallback.

Backend selection via AIPLAT_EMBED_BACKEND env var:
- hash (default): SHA-256 n-gram hash, 128-dim, zero-dependency
- transform: sentence-transformers (all-MiniLM-L6-v2), real semantic
- api: OpenAI-compatible embedding API
- deepseek: legacy alias → delegates to api

New: SemanticEmbedder class implements IEmbedder (from retriever.py) for use
by InMemoryRetriever and future VectorStoreRetriever.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any, List, Optional

# ── Hash fallback (synchronous, zero-dependency) ──────────────────────────

def hash_embed(text: str, dim: int = 128) -> List[float]:
    """SHA-256 n-gram hash → normalized float vector. Zero-dependency fallback."""
    if not text:
        return [0.0] * dim
    n = max(1, dim // 4)
    vec = [0.0] * dim
    for i in range(0, len(text) - n + 1, n):
        ngram = text[i: i + n].encode("utf-8", errors="ignore")
        h = int(hashlib.sha256(ngram).hexdigest()[:16], 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── Semantic embedding (synchronous, sentence-transformers) ───────────────

_semantic_model: Any = None
_semantic_model_name: Optional[str] = None


def _get_semantic_model() -> Any:
    global _semantic_model, _semantic_model_name
    name = os.getenv("AIPLAT_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    if _semantic_model is not None and _semantic_model_name == name:
        return _semantic_model
    # Try InfraEmbeddingAdapter first (unified model loading via infra)
    try:
        from core.harness.infrastructure.base_model_adapter import create_adapter
        _semantic_model = create_adapter("embedding", model_name=name)
        _semantic_model_name = name
        return _semantic_model
    except Exception:
        pass
    # Fallback: direct sentence-transformers (legacy, deprecated)
    try:
        from sentence_transformers import SentenceTransformer
        _semantic_model = SentenceTransformer(name)
        _semantic_model_name = name
        return _semantic_model
    except ImportError:
        return None


def embed_text_semantic(text: str) -> Optional[List[float]]:
    """Sync semantic embedding. Uses InfraEmbeddingAdapter when available."""
    model = _get_semantic_model()
    if model is None:
        return None
    # Check if it's InfraEmbeddingAdapter (uses embed_sync) or SentenceTransformer (uses encode)
    if hasattr(model, 'embed_sync'):
        return model.embed_sync(text)
    embedding = model.encode([text], show_progress_bar=False)
    return [float(v) for v in embedding[0]]


def embed_texts_semantic(texts: List[str]) -> Optional[List[List[float]]]:
    """Sync batch semantic embedding. Uses InfraEmbeddingAdapter when available."""
    model = _get_semantic_model()
    if model is None:
        return None
    if hasattr(model, 'embed_batch_sync'):
        return model.embed_batch_sync(texts)
    embeddings = model.encode(texts, show_progress_bar=False)
    return [[float(v) for v in emb] for emb in embeddings]


# ── Unified embed_text (router) ───────────────────────────────────────────

def _backend_name() -> str:
    return os.getenv("AIPLAT_EMBED_BACKEND", "hash").lower().strip()


async def embed_text(text: str, dim: int = 128) -> List[float]:
    """Unified async embed — selects backend via AIPLAT_EMBED_BACKEND."""
    backend = _backend_name()
    if backend == "hash":
        return hash_embed(text, dim)
    # Try semantic synchronous path first (sentence-transformers)
    vec = embed_text_semantic(text)
    if vec is not None:
        return vec
    # Try API via EmbeddingProvider
    if backend in ("api", "deepseek", "openai"):
        from core.harness.memory.embedding import get_embedding_provider
        try:
            provider = get_embedding_provider()
            return await provider.embed_single(text)
        except Exception:
            pass
    return hash_embed(text, dim)


async def embed_texts(texts: List[str], dim: int = 128) -> List[List[float]]:
    """Unified async batch embed — selects backend via AIPLAT_EMBED_BACKEND."""
    backend = _backend_name()
    if backend == "hash":
        return [hash_embed(t, dim) for t in texts]
    vecs = embed_texts_semantic(texts)
    if vecs is not None:
        return vecs
    if backend in ("api", "deepseek", "openai"):
        from core.harness.memory.embedding import get_embedding_provider
        try:
            provider = get_embedding_provider()
            return await provider.embed(texts)
        except Exception:
            pass
    return [hash_embed(t, dim) for t in texts]


# ── SemanticEmbedder (IEmbedder-compatible) ───────────────────────────────

class SemanticEmbedder:
    """IEmbedder-compatible semantic embedder using sentence-transformers / API.
    
    Usage:
        embedder = SemanticEmbedder()
        vec = await embedder.embed("some text")
        vecs = await embedder.embed_batch(["text1", "text2"])
    """
    
    def __init__(self, *, backend: str = "", model_name: str = ""):
        backend = backend or _backend_name()
        model_name = model_name or os.getenv(
            "AIPLAT_EMBEDDING_MODEL", "all-MiniLM-L6-v2"
        )
        self._backend = backend if backend != "hash" else "transform"
        self._model_name = model_name
    
    async def embed(self, text: str) -> List[float]:
        return await embed_text(text)
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return await embed_texts(texts)


def create_default_embedder():
    """Create the best available embedder (IEmbedder-compatible).
    
    Priority: sentence-transformers > API > hash fallback.
    """
    backend = _backend_name()
    if backend in ("transform", "api", "openai", "deepseek"):
        return SemanticEmbedder(backend=backend)
    from .retriever import HashEmbedder
    return HashEmbedder()


__all__ = [
    "hash_embed",
    "cosine_similarity",
    "embed_text",
    "embed_texts",
    "embed_text_semantic",
    "embed_texts_semantic",
    "SemanticEmbedder",
    "create_default_embedder",
]
