"""
Layer 3 (app) 指标采集器
"""

from typing import List
from .collector import MetricsCollector, Metric


class AppMetricsCollector(MetricsCollector):
    """Layer 3 (app) 指标采集器"""
    
    def __init__(self, endpoint: str = None):
        super().__init__("app", endpoint)
        
    async def collect(self) -> List[Metric]:
        """采集 app 层指标"""
        return [
            # Gateway 指标
            Metric(
                name="gateway_connections_active_count",
                value=50,
                labels={"type": "websocket"},
                unit="connections"
            ),
            Metric(
                name="gateway_messages_per_second",
                value=200,
                labels={"type": "all"},
                unit="mps"
            ),
            Metric(
                name="gateway_average_processing_time_milliseconds",
                value=10,
                labels={"type": "all"},
                unit="ms"
            ),
            
            # Channel 指标
            Metric(
                name="channels_active_count",
                value=3,
                labels={"type": "all"},
                unit="channels"
            ),
            Metric(
                name="channels_messages_sent_total",
                value=5000,
                labels={"type": "all"},
                unit="messages"
            ),
            Metric(
                name="channels_messages_received_total",
                value=5000,
                labels={"type": "all"},
                unit="messages"
            ),
            
            # Session 指标
            Metric(
                name="sessions_active_count",
                value=100,
                labels={"type": "all"},
                unit="sessions"
            ),
            Metric(
                name="sessions_average_duration_seconds",
                value=300,
                labels={"type": "all"},
                unit="seconds"
            )
        ]
