"""
Embedding adapter — delegates to core unified embedder via CoreFacade.

Re-exports core embedder functions for all KB code paths.
Cache lives in core/harness/knowledge/embedder.py (SemanticEmbedder + hash_embed).
"""
from __future__ import annotations

from typing import List
import math

from core.api.facades.kb_facade import kb_embed_text as _facade_embed

import os


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_text(text: str) -> List[float]:
    """Synchronous embed — uses CoreFacade kb_embed_text (hash by default)."""
    return _facade_embed(text)


async def embed_text_async(text: str) -> List[float]:
    """Async embed — attempts semantic, falls back to sync."""
    backend = os.getenv("AIPLAT_EMBED_BACKEND", "hash").lower().strip()
    if backend == "hash":
        return embed_text(text)
    try:
        from core.api.facades.kb_facade import kb_embed_text
        return kb_embed_text(text)
    except Exception:
        return embed_text(text)


async def embed_texts_async(texts: List[str]) -> List[List[float]]:
    return [await embed_text_async(t) for t in texts]
