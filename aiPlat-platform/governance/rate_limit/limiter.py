"""
Rate Limiter - 限流服务
"""

import time
from typing import Optional
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