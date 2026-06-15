"""
InfraEmbeddingAdapter — embedding through infra model management.
Inherits BaseModelAdapter for shared model resolution + caching.
"""

from __future__ import annotations

from typing import Any, List

from .base_model_adapter import BaseModelAdapter, get_cached_model


class InfraEmbeddingAdapter(BaseModelAdapter):
    capability = "embedding"

    def _load_model(self, name: str) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer(name, local_files_only=True)
        except ImportError:
            return None

    def embed_sync(self, text: str) -> List[float]:
        model = self._get_model()
        if model is None:
            raise RuntimeError("No embedding model available")
        embedding = model.encode([text], show_progress_bar=False)
        return [float(v) for v in embedding[0]]

    def embed_batch_sync(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        if model is None:
            raise RuntimeError("No embedding model available")
        embeddings = model.encode(texts, show_progress_bar=False)
        return [[float(v) for v in emb] for emb in embeddings]

    async def embed(self, text: str) -> List[float]:
        return self.embed_sync(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self.embed_batch_sync(texts)


def create_infra_embedding_adapter(**kwargs) -> InfraEmbeddingAdapter:
    return InfraEmbeddingAdapter(**kwargs)


def _get_semantic_model() -> Any:
    """Legacy loader — delegates to InfraEmbeddingAdapter for compat."""
    return get_cached_model("embedding", lambda name: InfraEmbeddingAdapter(model_name=name), model_name="")


__all__ = ["InfraEmbeddingAdapter", "create_infra_embedding_adapter", "_get_semantic_model"]
