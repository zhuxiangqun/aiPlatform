"""
Shared math utilities — single source of truth for cosine similarity and common ops.

Previously duplicated across 7 locations (long_term.py, semantic_cache.py, 
experience_vector.py, retriever.py, immune_memory.py, convergence.py).
All code should use these functions instead of reimplementing.

Migration: replace `self._cosine_similarity(a, b)` → `cosine_similarity(a, b)`.
"""

from __future__ import annotations
import math
from typing import List


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Standard cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
