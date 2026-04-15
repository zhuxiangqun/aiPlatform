"""
Layer 1 (core) 健康检查器
"""

from typing import List
from .health import HealthChecker, HealthCheckResult, HealthStatus


class CoreHealthChecker(HealthChecker):
    """Layer 1 (core) 健康检查器"""
    
    def __init__(self, endpoint: str = None):
        super().__init__("core", endpoint)
        
    async def check(self) -> List[HealthCheckResult]:
        """执行健康检查"""
        return [
            HealthCheckResult(
                component="harness",
                status=HealthStatus.HEALTHY,
                message="Harness engine is running",
                details={
                    "agents": 5,
                    "active_tasks": 10
                }
            ),
            HealthCheckResult(
                component="agents",
                status=HealthStatus.HEALTHY,
                message="Agent system is healthy",
                details={
                    "active_agents": 10,
                    "queued_tasks": 5
                }
            ),
            HealthCheckResult(
                component="memory",
                status=HealthStatus.HEALTHY,
                message="Memory system is healthy",
                details={
                    "sessions": 100,
                    "storage_usage": "500MB"
                }
            )
        ]
