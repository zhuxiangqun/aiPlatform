"""
API Gateway Router - API网关路由
"""

import re
from typing import Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


@dataclass
class Route:
    """路由定义"""
    path: str
    method: HttpMethod
    handler: Callable
    endpoint: str = ""
    rate_limit: int = 100
    timeout: int = 30


class GatewayRouter:
    """API网关路由器"""

    def __init__(self):
        self._routes: list[Route] = []
        self._path_patterns: dict[str, re.Pattern] = {}

    def register(
        self,
        path: str,
        method: HttpMethod,
        handler: Callable,
        endpoint: str = "",
        rate_limit: int = 100,
        timeout: int = 30,
    ) -> None:
        """注册路由"""
        route = Route(
            path=path,
            method=method,
            handler=handler,
            endpoint=endpoint,
            rate_limit=rate_limit,
            timeout=timeout,
        )
        self._routes.append(route)

    def match_route(self, path: str, method: str) -> Optional[Route]:
        """匹配路由"""
        for route in self._routes:
            if route.method.value != method:
                continue
            pattern = self._path_patterns.get(route.path)
            if pattern is None:
                pattern = re.compile(self._path_to_regex(route.path))
                self._path_patterns[route.path] = pattern

            if pattern.match(path):
                return route
        return None

    def _path_to_regex(self, path: str) -> str:
        """将路径转换为正则表达式"""
        regex = re.sub(r"\{[^}]+\}", r"[^/]+", path)
        regex = regex.replace("*", ".*")
        return f"^{regex}$"

    def list_routes(self) -> list[Route]:
        """列出所有路由"""
        return self._routes.copy()

    def get_routes_by_endpoint(self, endpoint: str) -> list[Route]:
        """获取指定端点的路由"""
        return [r for r in self._routes if r.endpoint == endpoint]


gateway_router = GatewayRouter()