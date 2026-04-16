"""
Layer 0 (infra) 健康检查器（HTTP 数据源）
"""

from typing import Optional

import httpx

from .http_health import HttpHealthChecker


class InfraHealthChecker(HttpHealthChecker):
    """通过 infra 层 /api/infra/health 获取权威健康结果（To‑Be）。"""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        super().__init__(
            layer="infra",
            endpoint=endpoint or "http://localhost:8001",
            health_path="/api/infra/health",
            timeout=timeout,
            transport=transport,
        )

