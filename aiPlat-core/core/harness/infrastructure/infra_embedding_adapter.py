"""
InfraEmbeddingAdapter — bridges core embedding to infra model management.

Replaces core's direct `import sentence_transformers` with a managed adapter.
Embedding model selection, loading, and lifecycle now go through infra's
ModelManager, consistent with the LLM path (InfraLLMAdapter).
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

_embedding_model_cache: Any = None
_embedding_model_name: Optional[str] = None


def _resolve_embedding_model_name() -> str:
    """Resolve embedding model name: env var → infra ModelManager → default."""
    model = os.getenv("AIPLAT_EMBEDDING_MODEL", "").strip()
    if model:
        return model
    # Try infra ModelManager for embedding models
    try:
        from infra.management.model.manager import ModelManager
        mgr = ModelManager()
        for m in mgr._models.values():
            if m.type.value == "embedding" and m.enabled:
                return m.name
    except Exception:
        pass
    return "all-MiniLM-L6-v2"


def _get_embedding_model():
    """Lazy-load the sentence-transformer model (singleton)."""
    global _embedding_model_cache, _embedding_model_name
    name = _resolve_embedding_model_name()
    if _embedding_model_cache is not None and _embedding_model_name == name:
        return _embedding_model_cache
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model_cache = SentenceTransformer(name)
        _embedding_model_name = name
        return _embedding_model_cache
    except ImportError:
        return None


class InfraEmbeddingAdapter:
    """
    Embedding adapter through infra model management.
    Uses sentence-transformers under the hood, but model selection
    goes through the unified config path (env vars → infra ModelManager).
    """

    def __init__(self, *, model_name: str = ""):
        self._model_name = model_name or _resolve_embedding_model_name()

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_sync(self, text: str) -> List[float]:
        """Synchronous single-text embedding."""
        model = _get_embedding_model()
        if model is None:
            raise RuntimeError("No embedding model available")
        embedding = model.encode([text], show_progress_bar=False)
        return [float(v) for v in embedding[0]]

    def embed_batch_sync(self, texts: List[str]) -> List[List[float]]:
        """Synchronous batch embedding."""
        model = _get_embedding_model()
        if model is None:
            raise RuntimeError("No embedding model available")
        embeddings = model.encode(texts, show_progress_bar=False)
        return [[float(v) for v in emb] for emb in embeddings]

    async def embed(self, text: str) -> List[float]:
        """Async single-text embedding (delegates to sync)."""
        return self.embed_sync(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Async batch embedding (delegates to sync)."""
        return self.embed_batch_sync(texts)


def create_infra_embedding_adapter() -> InfraEmbeddingAdapter:
    """Factory: create embedding adapter through infra."""
    return InfraEmbeddingAdapter()


__all__ = [
    "InfraEmbeddingAdapter",
    "create_infra_embedding_adapter",
    "_resolve_embedding_model_name",
]
