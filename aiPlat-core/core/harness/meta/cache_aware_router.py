"""CacheAwareRouter — 缓存感知路由。

核心逻辑: 在 ControlProfile 变更时评估对 provider-side prompt caching 的影响。
- D1+D2 cache_key_hash 不变 → 缓存前缀可复用 → 允许全部维度变动
- cache_key_hash 改变 → 冻结 D1/D2，仅允许 D3-D6 尾缀追加

Design:
  - 基于 ControlProfile.to_cache_key().cache_key_hash() 做 SHA256 比对
  - 离散化键 → 无浮点哈希漂移
  - TTL 过期后自动允许全量变动（避免缓存永久锁定）
  - update() 在每次 LLM 调用完成后更新基准键
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from .control_profile import ControlProfile

logger = logging.getLogger("aiplat.cache_router")


class CacheAwareRouter:
    """评估 ControlProfile 变更对 provider-side prompt caching 的影响。

    Usage:
        router = CacheAwareRouter(ttl_seconds=300)
        action = router.evaluate(current_profile)
        # action = {"freeze": ["D1","D2"], "allow": ["D3","D4","D5","D6"]}
        # 在 LLM 调用完成后: router.update(current_profile)
    """

    CACHE_SENSITIVE_DIMS = frozenset({
        "context_layers",
        "context_max_sources",
        "tool_whitelist",
        "tool_rank_by",
    })

    def __init__(self, ttl_seconds: int = 300):
        self._ttl = ttl_seconds
        self._last_key: Optional[str] = None
        self._last_timestamp: float = 0.0

    def evaluate(self, current: ControlProfile) -> Dict[str, List[str]]:
        """评估当前画像对缓存的影响。

        Returns:
            {"freeze": [...], "allow": [...]}
            freeze 中的维度在 PromptAssembler 中保持不变，
            allow 中的维度可以注入到 system prompt 非前缀部分。
        """
        now = time.time()
        current_key = current.cache_key_hash()

        # TTL 过期 → 全量允许
        if self._last_key is None or (now - self._last_timestamp) > self._ttl:
            self._last_key = current_key
            self._last_timestamp = now
            logger.debug("Cache TTL expired — full dimension change allowed")
            return {"freeze": [], "allow": ["D1", "D2", "D3", "D4", "D5", "D6"]}

        # cache key 不变 → 缓存前缀可复用，允许全量变动
        if current_key == self._last_key:
            logger.debug("Cache key unchanged (hash=%s) — full dimension change allowed", current_key[:8])
            return {"freeze": [], "allow": ["D1", "D2", "D3", "D4", "D5", "D6"]}

        # cache key 变了 → 冻结 D1/D2，仅允许 D3-D6
        logger.debug("Cache key changed (%s→%s) — freezing D1/D2",
                     self._last_key[:8], current_key[:8])
        return {"freeze": ["D1", "D2"], "allow": ["D3", "D4", "D5", "D6"]}

    def update(self, profile: ControlProfile) -> None:
        """更新缓存基准键（在 LLM 调用完成后调用）。"""
        self._last_key = profile.cache_key_hash()
        self._last_timestamp = time.time()

    def reset(self) -> None:
        """强制重置缓存基准（用于测试或会话切换）。"""
        self._last_key = None
        self._last_timestamp = 0.0


# ── Singleton ─────────────────────────────────────────────────

_router: Optional["CacheAwareRouter"] = None


def get_cache_router() -> CacheAwareRouter:
    global _router
    if _router is None:
        _router = CacheAwareRouter()
    return _router
