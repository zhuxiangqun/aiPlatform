"""
Gateway Service - 网关服务
"""

from typing import Any, Callable, Optional
import asyncio
from datetime import datetime
from enum import Enum


class GatewayMode(str, Enum):
    DIRECT = "direct"
    PROXY = "proxy"


class GatewayService:
    """网关服务"""

    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._middlewares: list[Callable] = []
        self._mode = GatewayMode.PROXY

    def register_handler(self, path: str, handler: Callable) -> None:
        """注册处理器"""
        self._handlers[path] = handler

    def add_middleware(self, middleware: Callable) -> None:
        """添加中间件"""
        self._middlewares.append(middleware)

    async def handle_request(
        self,
        path: str,
        method: str,
        headers: dict[str, str],
        body: Optional[bytes] = None,
    ) -> dict[str, Any]:
        """处理请求"""
        for middleware in self._middlewares:
            result = middleware(path, method, headers, body)
            if not result.get("allowed", True):
                return {"error": result.get("error", "Denied")}

        handler = self._handlers.get(path)
        if not handler:
            return {"error": "Not found", "status": 404}

        try:
            result = await handler(path, method, headers, body)
            return result
        except Exception as e:
            return {"error": str(e), "status": 500}

    def get_stats(self) -> dict[str, Any]:
        """获取统计"""
        return {
            "handlers_count": len(self._handlers),
            "middlewares_count": len(self._middlewares),
            "mode": self._mode.value,
        }


gateway_service = GatewayService()