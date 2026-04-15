"""
健康检查基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class HealthStatus(str, Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    component: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    

class HealthChecker(ABC):
    """健康检查器基类"""
    
    def __init__(self, layer: str, endpoint: str = None):
        self.layer = layer
        self.endpoint = endpoint
        
    @abstractmethod
    async def check(self) -> List[HealthCheckResult]:
        """执行健康检查"""
        pass
        
    async def get_health(self) -> Dict[str, Any]:
        """获取健康状态"""
        results = await self.check()
        
        overall_status = HealthStatus.HEALTHY
        for result in results:
            if result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED
            elif result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                
        return {
            "layer": self.layer,
            "status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": [self._result_to_dict(r) for r in results]
        }
        
    def _result_to_dict(self, result: HealthCheckResult) -> Dict[str, Any]:
        """转换结果为字典"""
        return {
            "component": result.component,
            "status": result.status.value,
            "message": result.message,
            "details": result.details,
            "timestamp": result.timestamp.isoformat()
        }
