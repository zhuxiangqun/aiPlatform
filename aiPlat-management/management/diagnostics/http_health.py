"""
HTTP-based HealthCheckers (design-correct implementation).

设计原则：
- management 仅聚合各层 health/diagnostics API 的结果
- 不在 management 进程内生成“权威健康状态”（避免本机探测/mock）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from .health import HealthChecker, HealthCheckResult, HealthStatus


def _to_status(value: str) -> HealthStatus:
    v = (value or "").lower()
    if v == "healthy":
        return HealthStatus.HEALTHY
    if v == "degraded":
        return HealthStatus.DEGRADED
    return HealthStatus.UNHEALTHY


class HttpHealthChecker(HealthChecker):
    """Fetch health checks from a remote layer via HTTP."""

    def __init__(
        self,
        layer: str,
        endpoint: str,
        health_path: str,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        super().__init__(layer=layer, endpoint=endpoint)
        self._health_path = health_path
        self._timeout = timeout
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.endpoint,
                timeout=self._timeout,
                transport=self._transport,
            )
        return self._client

    async def _fetch_json(self) -> Any:
        client = await self._get_client()
        resp = await client.get(self._health_path)
        resp.raise_for_status()
        return resp.json()

    async def check(self) -> List[HealthCheckResult]:
        """
        Normalize remote health response into list[HealthCheckResult].

        Supported shapes:
        1) infra style: {"status":"success","data":{name:{status,message,details,timestamp}}}
        2) generic style: {"status":"healthy", ...}
        """
        try:
            payload = await self._fetch_json()
        except Exception as e:
            return [
                HealthCheckResult(
                    component=f"{self.layer}_health_endpoint",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health endpoint unavailable: {e}",
                    details={"endpoint": self.endpoint, "path": self._health_path},
                )
            ]

        # infra style
        if isinstance(payload, dict) and payload.get("status") == "success" and isinstance(payload.get("data"), dict):
            results: List[HealthCheckResult] = []
            for name, item in payload["data"].items():
                if isinstance(item, dict):
                    results.append(
                        HealthCheckResult(
                            component=str(name),
                            status=_to_status(str(item.get("status", "unhealthy"))),
                            message=str(item.get("message", "")),
                            details=item.get("details") if isinstance(item.get("details"), dict) else {"raw": item},
                        )
                    )
                else:
                    results.append(
                        HealthCheckResult(
                            component=str(name),
                            status=_to_status(str(item)),
                            message="",
                            details={},
                        )
                    )
            return results

        # generic style
        if isinstance(payload, dict) and "status" in payload:
            return [
                HealthCheckResult(
                    component=f"{self.layer}_service",
                    status=_to_status(str(payload.get("status"))),
                    message=str(payload.get("message", "")),
                    details={k: v for k, v in payload.items() if k not in ("status", "message")},
                )
            ]

        # unknown
        return [
            HealthCheckResult(
                component=f"{self.layer}_health_unknown",
                status=HealthStatus.DEGRADED,
                message="Unknown health response shape",
                details={"payload": payload},
            )
        ]

