"""
Gateway Filter - 网关过滤器
"""

from typing import Callable, Any, Optional
from dataclasses import dataclass


@dataclass
class FilterContext:
    """过滤器上下文"""
    path: str
    method: str
    headers: dict[str, str]
    query_params: dict[str, str]
    body: Any = None
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None


class FilterResult:
    """过滤器结果"""

    def __init__(self, allowed: bool, error: Optional[str] = None):
        self.allowed = allowed
        self.error = error


class Filter(Callable[[FilterContext], FilterResult]):
    """网关过滤器基类"""

    def __init__(self, name: str, order: int = 0):
        self.name = name
        self.order = order

    def __call__(self, context: FilterContext) -> FilterResult:
        raise NotImplementedError


class AuthFilter(Filter):
    """认证过滤器"""

    def __init__(self):
        super().__init__("auth", order=10)

    def __call__(self, context: FilterContext) -> FilterResult:
        api_key = context.headers.get("Authorization", "").replace("Bearer ", "")
        if not api_key:
            return FilterResult(allowed=False, error="Missing authorization")
        return FilterResult(allowed=True)


class RateLimitFilter(Filter):
    """限流过滤器"""

    def __init__(self, max_requests: int = 100):
        super().__init__("rate_limit", order=20)
        self.max_requests = max_requests
        self._request_counts: dict[str, int] = {}

    def __call__(self, context: FilterContext) -> FilterResult:
        tenant_id = context.tenant_id or "default"
        count = self._request_counts.get(tenant_id, 0)

        if count >= self.max_requests:
            return FilterResult(allowed=False, error="Rate limit exceeded")

        self._request_counts[tenant_id] = count + 1
        return FilterResult(allowed=True)


class TenantFilter(Filter):
    """租户过滤器"""

    def __init__(self):
        super().__init__("tenant", order=5)

    def __call__(self, context: FilterContext) -> FilterResult:
        tenant_id = context.headers.get("X-AIPLAT-TENANT-ID", "default")
        context.tenant_id = tenant_id
        return FilterResult(allowed=True)


class FilterChain:
    """过滤器链"""

    def __init__(self):
        self._filters: list[Filter] = []

    def add_filter(self, filter: Filter) -> None:
        self._filters.append(filter)
        self._filters.sort(key=lambda f: f.order)

    def process(self, context: FilterContext) -> FilterResult:
        for filter in self._filters:
            result = filter(context)
            if not result.allowed:
                return result
        return FilterResult(allowed=True)


filter_chain = FilterChain()