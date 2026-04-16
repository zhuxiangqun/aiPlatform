"""
Layer 2 (platform) 健康检查器（HTTP 数据源）
"""

from typing import Optional

import httpx

from .http_health import HttpHealthChecker


class PlatformHealthChecker(HttpHealthChecker):
    """通过 platform 层 /health 获取权威健康结果（To‑Be）。"""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        super().__init__(
            layer="platform",
            endpoint=endpoint or "http://localhost:8003",
            health_path="/health",
            timeout=timeout,
            transport=transport,
        )

