"""Semantic cache — reusable check/write for any Agent.

Wraps the materials_chat.py 4-point cache pattern into two functions:
  - try_cache_hit(query, domain_id) → Optional[dict]
  - write_cache_result(query, domain_id, answer, citations)

Any Agent can import and call these without duplicating cache logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("aiplat.semantic_cache_hook")


async def try_cache_hit(question: str, domain_id: str) -> Optional[Dict[str, Any]]:
    """Check semantic cache (L1 exact + L2 embedding similarity).

    Returns a dict with answer/citations/level if found, None otherwise.
    """
    try:
        from core.harness.knowledge.semantic_cache import get_semantic_cache

        cache = get_semantic_cache()
        if not cache.enabled:
            return None

        cached = await cache.get(question, domain_id)
        if cached and isinstance(cached, dict) and cached.get("answer"):
            return {
                "answer": cached["answer"],
                "citations": cached.get("citations", []),
                "level": cached.get("level", "L1"),
            }
        return None
    except Exception as e:
        logger.debug("cache check failed: %s", e)
        return None


async def write_cache_result(
    question: str,
    domain_id: str,
    answer: str,
    citations: Optional[list] = None,
) -> bool:
    """Write successful result to semantic cache for future reuse.

    Returns True if write succeeded.
    """
    try:
        from core.harness.knowledge.semantic_cache import get_semantic_cache

        cache = get_semantic_cache()
        if not cache.enabled:
            return False

        payload: dict = {
            "answer": answer,
            "citations": citations or [],
        }
        await cache.set(question, domain_id, payload)
        return True
    except Exception as e:
        logger.debug("cache write failed: %s", e)
        return False
