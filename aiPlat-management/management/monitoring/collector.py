"""
监控指标采集器基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Metric:
    """监控指标"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
            "unit": self.unit
        }


class MetricsCollector(ABC):
    """指标采集器基类"""
    
    def __init__(self, layer: str, endpoint: str = None):
        self.layer = layer
        self.endpoint = endpoint
        
    @abstractmethod
    async def collect(self) -> List[Metric]:
        """采集指标"""
        pass
        
    async def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        metrics = await self.collect()
        return {
            "layer": self.layer,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": [m.to_dict() for m in metrics]
        }
