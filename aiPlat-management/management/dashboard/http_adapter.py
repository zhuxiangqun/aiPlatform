"""
HTTP adapters for dashboard aggregation (To‑Be design).

设计原则：
- management 作为管理平面，只通过 HTTP 调用各层管理 API 获取数据
- 不在 management 进程内做本机探测作为权威数据源
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class HttpLayerAdapterConfig:
    layer: str
    endpoint: str
    status_path: str
    health_path: str
    metrics_path: str
    timeout: float = 30.0


class HttpLayerAdapter:
    """Generic HTTP adapter: status/health/metrics."""

    def __init__(self, config: HttpLayerAdapterConfig, transport: Optional[httpx.BaseTransport] = None):
        self._cfg = config
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._cfg.endpoint,
                timeout=self._cfg.timeout,
                transport=self._transport,
            )
        return self._client

    async def _get_json(self, path: str) -> Any:
        client = await self._get_client()
        resp = await client.get(path)
        resp.raise_for_status()
        return resp.json()

    async def get_status(self) -> Dict[str, Any]:
        """
        Return a dashboard-friendly status dict.
        If remote is unavailable, return status=error with error message.
        """
        try:
            payload = await self._get_json(self._cfg.status_path)
            # Normalize common response shapes:
            # - {"status":"success","data":{...}}
            # - {"layer":"infra","status":"healthy",...}
            data = payload.get("data") if isinstance(payload, dict) else None
            if data is not None and isinstance(payload, dict):
                return {"layer": self._cfg.layer, "status": "healthy", "data": data}
            if isinstance(payload, dict) and "layer" in payload and "status" in payload:
                return payload
            return {"layer": self._cfg.layer, "status": "healthy", "data": payload}
        except Exception as e:
            return {"layer": self._cfg.layer, "status": "error", "error": str(e)}

    async def health_check(self) -> bool:
        try:
            payload = await self._get_json(self._cfg.health_path)
            if isinstance(payload, dict) and payload.get("status") == "success":
                # infra style: {"status":"success","data":{...}}
                return True
            if isinstance(payload, dict) and payload.get("status") == "healthy":
                return True
            return True
        except Exception:
            return False

    async def get_metrics(self) -> Dict[str, Any]:
        try:
            payload = await self._get_json(self._cfg.metrics_path)
            if isinstance(payload, dict) and "data" in payload:
                return payload["data"] if isinstance(payload["data"], dict) else {"data": payload["data"]}
            return payload if isinstance(payload, dict) else {"data": payload}
        except Exception as e:
            return {"error": str(e)}


def create_default_http_adapter(layer: str, endpoint: str) -> HttpLayerAdapter:
    """
    Default adapter mapping for aiPlat layers.
    - infra: /api/infra/{status,health,metrics}
    - core:  /api/core/{health} (status/metrics are best-effort placeholders until core exposes explicit endpoints)
    - platform/app: assume /health for now (placeholders)
    """
    layer_lower = (layer or "").lower()
    if layer_lower == "infra":
        cfg = HttpLayerAdapterConfig(
            layer="infra",
            endpoint=endpoint,
            status_path="/api/infra/status",
            health_path="/api/infra/health",
            metrics_path="/api/infra/metrics",
        )
        return HttpLayerAdapter(cfg)

    if layer_lower == "core":
        cfg = HttpLayerAdapterConfig(
            layer="core",
            endpoint=endpoint,
            status_path="/api/core/health",
            health_path="/api/core/health",
            metrics_path="/api/core/permissions/stats",
        )
        return HttpLayerAdapter(cfg)

    # platform/app placeholders
    cfg = HttpLayerAdapterConfig(
        layer=layer_lower,
        endpoint=endpoint,
        status_path="/health",
        health_path="/health",
        metrics_path="/metrics",
    )
    return HttpLayerAdapter(cfg)


class InfraHttpAdapter(HttpLayerAdapter):
    """Dashboard adapter for Layer 0 (infra) via HTTP."""

    def __init__(self, endpoint: str = "http://localhost:8001", timeout: float = 30.0, transport: Optional[httpx.BaseTransport] = None):
        cfg = HttpLayerAdapterConfig(
            layer="infra",
            endpoint=endpoint,
            status_path="/api/infra/status",
            health_path="/api/infra/health",
            metrics_path="/api/infra/metrics",
            timeout=timeout,
        )
        super().__init__(cfg, transport=transport)


class CoreHttpAdapter(HttpLayerAdapter):
    """Dashboard adapter for Layer 1 (core) via HTTP (best-effort)."""

    def __init__(self, endpoint: str = "http://localhost:8002", timeout: float = 30.0, transport: Optional[httpx.BaseTransport] = None):
        cfg = HttpLayerAdapterConfig(
            layer="core",
            endpoint=endpoint,
            status_path="/api/core/health",
            health_path="/api/core/health",
            metrics_path="/api/core/permissions/stats",
            timeout=timeout,
        )
        super().__init__(cfg, transport=transport)


class PlatformHttpAdapter(HttpLayerAdapter):
    def __init__(self, endpoint: str = "http://localhost:8003", timeout: float = 30.0, transport: Optional[httpx.BaseTransport] = None):
        cfg = HttpLayerAdapterConfig(
            layer="platform",
            endpoint=endpoint,
            status_path="/health",
            health_path="/health",
            metrics_path="/metrics",
            timeout=timeout,
        )
        super().__init__(cfg, transport=transport)


class AppHttpAdapter(HttpLayerAdapter):
    def __init__(self, endpoint: str = "http://localhost:8004", timeout: float = 30.0, transport: Optional[httpx.BaseTransport] = None):
        cfg = HttpLayerAdapterConfig(
            layer="app",
            endpoint=endpoint,
            status_path="/health",
            health_path="/health",
            metrics_path="/metrics",
            timeout=timeout,
        )
        super().__init__(cfg, transport=transport)
