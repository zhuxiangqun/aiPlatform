"""
Layer 2 (platform) 指标采集器
"""

from typing import List
from .collector import MetricsCollector, Metric


class PlatformMetricsCollector(MetricsCollector):
    """Layer 2 (platform) 指标采集器"""
    
    def __init__(self, endpoint: str = None):
        super().__init__("platform", endpoint)
        
    async def collect(self) -> List[Metric]:
        """采集 platform 层指标"""
        return [
            # API 指标
            Metric(
                name="api_requests_per_second",
                value=100,
                labels={"endpoint": "all"},
                unit="rps"
            ),
            Metric(
                name="api_average_response_time_milliseconds",
                value=50,
                labels={"endpoint": "all"},
                unit="ms"
            ),
            Metric(
                name="api_error_rate",
                value=0.01,
                labels={"endpoint": "all"},
                unit="ratio"
            ),
            
            # Auth 指标
            Metric(
                name="auth_active_tokens_count",
                value=500,
                labels={"type": "jwt"},
                unit="tokens"
            ),
            Metric(
                name="auth_authentications_total",
                value=1000,
                labels={"type": "jwt"},
                unit="authentications"
            ),
            Metric(
                name="auth_failed_attempts_total",
                value=10,
                labels={"type": "jwt"},
                unit="attempts"
            ),
            
            # Tenant 指标
            Metric(
                name="tenants_count",
                value=10,
                labels={"type": "all"},
                unit="tenants"
            ),
            Metric(
                name="tenants_active_users_count",
                value=100,
                labels={"type": "all"},
                unit="users"
            )
        ]
