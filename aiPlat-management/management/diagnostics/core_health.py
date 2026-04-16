"""
Layer 1 (core) 健康检查器（HTTP 数据源）
"""

from typing import Optional

import httpx

from .http_health import HttpHealthChecker


class CoreHealthChecker(HttpHealthChecker):
    """通过 core 层 /api/core/health 获取权威健康结果（To‑Be）。"""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        super().__init__(
            layer="core",
            endpoint=endpoint or "http://localhost:8002",
            health_path="/api/core/health",
            timeout=timeout,
            transport=transport,
        )

