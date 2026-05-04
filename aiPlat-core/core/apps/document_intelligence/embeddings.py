from __future__ import annotations

import hashlib
import math
import os
from typing import List


def _hash_embedding(text: str, dim: int = 128) -> List[float]:
    """
    Deterministic fallback embedding.
    - No external dependency
    - Good enough for MVP smoke / semantic-ish retrieval baseline
    """
    text = (text or "").strip()
    if not text:
        return [0.0] * dim
    vec = [0.0] * dim
    # Character n-gram-ish hashing
    data = text.encode("utf-8", errors="ignore")
    for i in range(max(1, len(data))):
        chunk = data[i : i + 3] if i + 3 <= len(data) else data[i:]
        h = hashlib.sha256(chunk).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if (h[4] % 2 == 0) else -1.0
        vec[idx] += sign
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_text(text: str) -> List[float]:
    """
    Embedding entry point.
    Current MVP uses deterministic hash embeddings.
    Future:
    - support OpenAI-compatible embedding endpoint via env
    """
    dim = int(os.getenv("AIPLAT_EMBED_DIM", "128"))
    return _hash_embedding(text, dim=dim)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))

