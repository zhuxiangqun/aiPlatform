from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_EMBED_CACHE: dict = {}
_EMBED_CACHE_MAX = 2048


def _hash_embedding(text: str, dim: int = 128) -> List[float]:
    text = (text or "").strip()
    if not text:
        return [0.0] * dim
    vec = [0.0] * dim
    data = text.encode("utf-8", errors="ignore")
    for i in range(max(1, len(data))):
        chunk = data[i : i + 3] if i + 3 <= len(data) else data[i:]
        h = hashlib.sha256(chunk).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if (h[4] % 2 == 0) else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _get_async_embedder():
    provider = os.getenv("AIPLAT_EMBED_PROVIDER", "hash").lower().strip()
    if provider == "hash":
        return None
    try:
        if provider in ("openai", "deepseek"):
            from infra.llm.providers.openai import OpenAIProvider
            from infra.llm.providers.deepseek import DeepSeekProvider
            if provider == "openai":
                return OpenAIProvider()
            return DeepSeekProvider()
    except Exception as e:
        logger.warning("Failed to load embed provider '%s': %s", provider, e)
    return None


def embed_text(text: str) -> List[float]:
    dim = int(os.getenv("AIPLAT_EMBED_DIM", "128"))
    cache_key = f"h:{hashlib.sha256(text.encode()).hexdigest()}:{dim}"
    if cache_key in _EMBED_CACHE:
        return _EMBED_CACHE[cache_key]
    vec = _hash_embedding(text, dim=dim)
    if len(_EMBED_CACHE) < _EMBED_CACHE_MAX:
        _EMBED_CACHE[cache_key] = vec
    return vec


async def embed_text_async(text: str) -> List[float]:
    embedder = _get_async_embedder()
    if embedder is None:
        return embed_text(text)
    cache_key = f"a:{hashlib.sha256(text.encode()).hexdigest()}"
    if cache_key in _EMBED_CACHE:
        return _EMBED_CACHE[cache_key]
    try:
        result = await embedder.embed([text])
        if result and hasattr(result, "data") and result.data:
            vec = result.data[0].embedding if hasattr(result.data[0], "embedding") else result.data[0]
            if isinstance(vec, list) and len(vec) > 0:
                if len(_EMBED_CACHE) < _EMBED_CACHE_MAX:
                    _EMBED_CACHE[cache_key] = vec
                return vec
    except Exception as e:
        logger.warning("Async embed failed, falling back to hash: %s", e)
    return embed_text(text)


async def embed_texts_async(texts: List[str]) -> List[List[float]]:
    embedder = _get_async_embedder()
    if embedder is None:
        return [embed_text(t) for t in texts]
    try:
        result = await embedder.embed(texts)
        if result and hasattr(result, "data") and result.data:
            vecs = []
            for d in result.data:
                v = d.embedding if hasattr(d, "embedding") else d
                if isinstance(v, list):
                    vecs.append(v)
            if vecs and len(vecs) == len(texts):
                return vecs
    except Exception as e:
        logger.warning("Async batch embed failed, falling back to hash: %s", e)
    return [embed_text(t) for t in texts]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))

