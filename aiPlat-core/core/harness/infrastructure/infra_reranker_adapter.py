"""
InfraRerankerAdapter — bridges core reranker to infra model management.

Wraps sentence-transformers CrossEncoder through a managed adapter
consistent with the LLM (InfraLLMAdapter) and Embedding (InfraEmbeddingAdapter) paths.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

_rerank_model_cache: Any = None
_rerank_model_name: Optional[str] = None


def _resolve_rerank_model_name() -> str:
    return os.getenv("AIPLAT_RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual")


def _get_rerank_model():
    global _rerank_model_cache, _rerank_model_name
    name = _resolve_rerank_model_name()
    if _rerank_model_cache is not None and _rerank_model_name == name:
        return _rerank_model_cache
    try:
        from sentence_transformers import CrossEncoder
        _rerank_model_cache = CrossEncoder(name, max_length=512, trust_remote_code=True)
        _rerank_model_name = name
        return _rerank_model_cache
    except ImportError:
        return None


class InfraRerankerAdapter:
    """Reranker adapter through infra model management."""

    def __init__(self, *, model_name: str = ""):
        self._model_name = model_name or _resolve_rerank_model_name()

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 8) -> Optional[List[Dict[str, Any]]]:
        model = _get_rerank_model()
        if model is None:
            return None
        pairs = [(query, str(c.get("text", "")[:2000])) for c in candidates]
        scores = model.predict(pairs)
        scored = list(zip(scores, candidates))
        scored.sort(key=lambda x: x[0], reverse=True)
        result = [c for _, c in scored[:top_k]]
        for i, c in enumerate(result):
            c["score"] = float(scores[i]) if i < len(scores) else c.get("score", 0.0)
        return result


def create_infra_reranker_adapter() -> InfraRerankerAdapter:
    return InfraRerankerAdapter()


__all__ = ["InfraRerankerAdapter", "create_infra_reranker_adapter"]
