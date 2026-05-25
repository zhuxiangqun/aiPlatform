"""
InfraRerankerAdapter — cross-encoder reranker through infra model management.
Inherits BaseModelAdapter for shared model resolution + caching.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_model_adapter import BaseModelAdapter


class InfraRerankerAdapter(BaseModelAdapter):
    capability = "reranker"

    def _load_model(self, name: str) -> Any:
        try:
            from sentence_transformers import CrossEncoder
            return CrossEncoder(name, max_length=512, trust_remote_code=True)
        except ImportError:
            return None

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 8) -> Optional[List[Dict[str, Any]]]:
        model = self._get_model()
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


def create_infra_reranker_adapter(**kwargs) -> InfraRerankerAdapter:
    return InfraRerankerAdapter(**kwargs)


__all__ = ["InfraRerankerAdapter", "create_infra_reranker_adapter"]
