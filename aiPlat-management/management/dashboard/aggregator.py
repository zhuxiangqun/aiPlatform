"""
Dashboard 聚合器 - 聚合各层状态数据
"""

from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class LayerStatus:
    """层级状态"""
    layer: str
    status: str  # healthy, degraded, unhealthy
    uptime: int
    last_check: datetime
    metrics: Dict[str, Any] = field(default_factory=dict)
    issues: list = field(default_factory=list)
    

class DashboardAggregator:
    """Dashboard 数据聚合器"""
    
    def __init__(self):
        self.adapters: Dict[str, Any] = {}
        
    def register_adapter(self, layer: str, adapter: Any):
        """注册层级适配器"""
        self.adapters[layer] = adapter
        
    async def aggregate(self) -> Dict[str, Any]:
        """聚合所有层级状态"""
        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "layers": {},
            "overall_status": "healthy",
            "summary": {
                "total_layers": len(self.adapters),
                "healthy_layers": 0,
                "degraded_layers": 0,
                "unhealthy_layers": 0
            }
        }
        
        for layer, adapter in self.adapters.items():
            try:
                status = await adapter.get_status()
                result["layers"][layer] = status
                
                # 统计状态
                if status.get("status") == "healthy":
                    result["summary"]["healthy_layers"] += 1
                elif status.get("status") == "degraded":
                    result["summary"]["degraded_layers"] += 1
                    result["overall_status"] = "degraded"
                else:
                    result["summary"]["unhealthy_layers"] += 1
                    result["overall_status"] = "unhealthy"
                    
            except Exception as e:
                result["layers"][layer] = {
                    "status": "error",
                    "error": str(e)
                }
                result["overall_status"] = "unhealthy"
                
        return result
        
    async def get_health(self) -> Dict[str, bool]:
        """获取健康检查结果"""
        health = {}
        for layer, adapter in self.adapters.items():
            try:
                status = await adapter.health_check()
                health[layer] = status
            except Exception:
                health[layer] = False
        return health
        
    async def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """获取所有层级指标"""
        metrics = {}
        for layer, adapter in self.adapters.items():
            try:
                layer_metrics = await adapter.get_metrics()
                metrics[layer] = layer_metrics
            except Exception as e:
                metrics[layer] = {"error": str(e)}
        return metrics
