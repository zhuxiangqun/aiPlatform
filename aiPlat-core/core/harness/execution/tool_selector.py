"""
ToolSelector — select most relevant tools for the current task via semantic matching.

Reduces token cost when tool count exceeds SELECT_THRESHOLD (default 15).
Uses lightweight keyword-based similarity by default; embedding-based via
sentence_transformers if available (opt-in: AIPLAT_TOOL_SELECTOR_EMBEDDING=1).

Config:
  AIPLAT_TOOL_SELECTOR_MAX=10     → top-K tools to include in prompt
  AIPLAT_TOOL_SELECTOR_THRESHOLD=15 → only select when tools > threshold
  AIPLAT_TOOL_SELECTOR_EMBEDDING=0  → use keyword matching (default)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple


class ToolSelector:
    def __init__(self, max_tools: int = None, threshold: int = None):
        self._max = max_tools or int(os.getenv("AIPLAT_TOOL_SELECTOR_MAX", "10"))
        self._threshold = threshold or int(os.getenv("AIPLAT_TOOL_SELECTOR_THRESHOLD", "5"))
        self._use_embedding = os.getenv("AIPLAT_TOOL_SELECTOR_EMBEDDING", "0") in ("1", "true", "yes")
        self._embedder = None

    def _ensure_embedder(self):
        if self._embedder is not None:
            return
        try:
            from core.harness.infrastructure.base_model_adapter import create_adapter
            self._embedder = create_adapter("embedding")
        except Exception:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", local_files_only=True)
            except Exception:
                self._use_embedding = False
                self._embedder = False  # tried, failed

    def select(self, prompt: str, tools: List[Any]) -> List[Any]:
        """Return top-K most relevant tools for the given prompt."""
        if len(tools) <= self._threshold:
            return list(tools)

        scored = self._score_tools(prompt, tools)
        scored.sort(key=lambda x: x[1], reverse=True)
        top = [t for t, _ in scored[:self._max]]

        # Always include tool_search (dynamic discovery) if present
        discovery_names = {"tool_search", "search_tools", "list_tools"}
        for t in tools:
            name = getattr(t, 'name', '') or getattr(getattr(t, '_config', None), 'name', '') or ''
            if name in discovery_names and t not in top:
                top.insert(0, t)
                break
        return top

    def _score_tools(self, prompt: str, tools: List[Any]) -> List[Tuple[Any, float]]:
        if self._use_embedding:
            return self._score_embedding(prompt, tools)
        return self._score_keyword(prompt, tools)

    def _score_embedding(self, prompt: str, tools: List[Any]) -> List[Tuple[Any, float]]:
        self._ensure_embedder()
        if not self._embedder or self._embedder is False:
            return self._score_keyword(prompt, tools)

        import numpy as np
        try:
            prompt_vec = self._embedder.encode([prompt[:1000]], convert_to_numpy=True)[0]
        except Exception:
            return self._score_keyword(prompt, tools)

        results = []
        for t in tools:
            desc = self._tool_text(t)[:500]
            try:
                vec = self._embedder.encode([desc], convert_to_numpy=True)[0]
                sim = float(np.dot(prompt_vec, vec) / (np.linalg.norm(prompt_vec) * np.linalg.norm(vec) + 1e-8))
            except Exception:
                sim = self._keyword_sim(prompt, desc)
            results.append((t, sim))
        return results

    def _score_keyword(self, prompt: str, tools: List[Any]) -> List[Tuple[Any, float]]:
        results = []
        for t in tools:
            desc = self._tool_text(t)
            sim = self._keyword_sim(prompt, desc)
            results.append((t, sim))
        return results

    @staticmethod
    def _tool_text(tool: Any) -> str:
        parts = []
        name = getattr(tool, 'name', '') or getattr(getattr(tool, '_config', None), 'name', '') or ''
        desc = getattr(tool, 'description', '') or getattr(getattr(tool, '_config', None), 'description', '') or ''
        if name:
            parts.append(name)
        if desc:
            parts.append(str(desc)[:400])
        input_schema = getattr(tool, 'input_schema', None) or getattr(getattr(tool, '_config', None), 'input_schema', None)
        if isinstance(input_schema, dict):
            parts.append(" ".join(str(k) for k in input_schema.keys())[:200])
        return " ".join(parts).lower()

    @staticmethod
    def _keyword_sim(prompt: str, desc: str) -> float:
        """Weighted keyword overlap score (TF-IDF-like, no external deps)."""
        p_words = set(re.findall(r'\w{3,}', prompt.lower()))
        d_words = set(re.findall(r'\w{3,}', desc.lower()))
        if not p_words or not d_words:
            return 0.0
        # Jaccard similarity with IDF-like penalty for overly common words
        common_stopwords = {"the", "and", "for", "that", "this", "with", "from", "each", "will",
                           "should", "must", "have", "been", "when", "where", "what", "which",
                           "your", "into", "over", "also", "then", "than", "very", "just", "only"}
        p_filtered = p_words - common_stopwords
        d_filtered = d_words - common_stopwords

        overlap = p_filtered & d_filtered
        size = min(len(p_filtered), len(d_filtered))
        if size == 0:
            return 0.0
        return len(overlap) / size


# Global singleton
def get_tool_selector() -> ToolSelector:
    return ToolSelector()
