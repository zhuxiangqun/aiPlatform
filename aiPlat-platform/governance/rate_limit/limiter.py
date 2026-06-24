"""
Rate Limiter - 限流服务
"""

import os
import time
from typing import Any, Optional
from threading import Lock


class RateLimitExceeded(Exception):
    """限流异常"""
    pass


class RateLimiter:
    """限流服务"""

    def __init__(self):
        self._limits: dict[str, dict] = {}
        self._buckets: dict[str, list[float]] = {}
        self._lock = Lock()

    def set_limit(self, key: str, max_requests: int, window_seconds: int = 60) -> None:
        """设置限流规则"""
        self._limits[key] = {
            "max_requests": max_requests,
            "window_seconds": window_seconds,
        }

    def check(self, key: str) -> bool:
        """检查是否允许请求"""
        with self._lock:
            if key not in self._limits:
                return True

            limit = self._limits[key]
            max_requests = limit["max_requests"]
            window = limit["window_seconds"]

            now = time.time()
            if key not in self._buckets:
                self._buckets[key] = []

            self._buckets[key] = [
                t for t in self._buckets[key] if now - t < window
            ]

            return len(self._buckets[key]) < max_requests

    def consume(self, key: str) -> bool:
        """消费一个请求"""
        if not self.check(key):
            return False

        with self._lock:
            if key in self._buckets:
                self._buckets[key].append(time.time())
            else:
                self._buckets[key] = [time.time()]
        return True

    def get_remaining(self, key: str) -> int:
        """获取剩余请求数"""
        with self._lock:
            if key not in self._limits or key not in self._buckets:
                limit = self._limits.get(key, {}).get("max_requests", 100)
                return limit

            limit = self._limits[key]
            max_requests = limit["max_requests"]
            window = limit["window_seconds"]

            now = time.time()
            recent = [
                t for t in self._buckets[key] if now - t < window
            ]
            return max(0, max_requests - len(recent))

    def reset(self, key: str) -> None:
        """重置限流"""
        with self._lock:
            if key in self._buckets:
                self._buckets[key] = []


rate_limiter = RateLimiter()


# ── 分布式限流：Redis 后端令牌桶 ──

class RedisRateLimiter:
    """基于 Redis 的分布式令牌桶限流器。

    适用于多实例部署场景，替代单进程 in-memory RateLimiter。

    环境变量:
      AIPLAT_RATE_LIMIT_REDIS_URL: Redis 连接 URL (默认: redis://localhost:6379)
      AIPLAT_RATE_LIMIT_DEFAULT_RATE: 默认每秒请求数 (默认: 100)
    """

    def __init__(self):
        self._redis_url = os.getenv("AIPLAT_RATE_LIMIT_REDIS_URL", "")
        self._default_rate = int(os.getenv("AIPLAT_RATE_LIMIT_DEFAULT_RATE", "100"))
        self._redis: Any = None

    async def _ensure_redis(self) -> bool:
        if self._redis is not None:
            return True
        if not self._redis_url:
            return False
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.Redis.from_url(self._redis_url)
            return True
        except ImportError:
            return False
        except Exception:
            return False

    async def check(self, key: str, max_tokens: int = 0, window: int = 60) -> bool:
        """检查是否允许请求（原子操作，Lua 脚本）。"""
        if not await self._ensure_redis():
            return True  # Redis 不可用 → 放行（避免误拦）

        max_t = max_tokens or self._default_rate
        script = """
        local current = redis.call('GET', KEYS[1])
        if current and tonumber(current) >= tonumber(ARGV[1]) then
            return 0
        end
        redis.call('INCR', KEYS[1])
        redis.call('EXPIRE', KEYS[1], ARGV[2])
        return 1
        """
        try:
            result = await self._redis.eval(script, 1, key, max_t, window)
            return bool(result)
        except Exception:
            return True  # Redis 异常 → 放行（避免误拦）

    async def get_remaining(self, key: str, max_tokens: int = 0) -> int:
        if not await self._ensure_redis():
            return -1
        max_t = max_tokens or self._default_rate
        current = await self._redis.get(key)
        return max_t - int(current or 0)

    async def reset(self, key: str) -> None:
        if await self._ensure_redis():
            await self._redis.delete(key)


_redis_limiter: Optional[RedisRateLimiter] = None


def get_redis_rate_limiter() -> RedisRateLimiter:
    global _redis_limiter
    if _redis_limiter is None:
        _redis_limiter = RedisRateLimiter()
    return _redis_limiter