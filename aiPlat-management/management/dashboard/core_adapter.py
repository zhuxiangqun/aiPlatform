"""
Layer 1 (core) 适配器
"""

from typing import Dict, Any


class CoreAdapter:
    """Layer 1 (core) Dashboard 适配器"""
    
    def __init__(self, endpoint: str = None):
        self.endpoint = endpoint or "http://localhost:8002"
        self.layer_name = "core"
        
    async def get_status(self) -> Dict[str, Any]:
        """获取 core 层状态"""
        return {
            "layer": self.layer_name,
            "status": "healthy",
            "score": 100,
            "uptime": 86400,
            "components": {
                "harness": {"status": "healthy", "agents": 5},
                "agents": {"status": "healthy", "active": 10},
                "skills": {"status": "healthy", "registered": 50},
                "memory": {"status": "healthy", "sessions": 100}
            }
        }
        
    async def health_check(self) -> bool:
        """健康检查"""
        status = await self.get_status()
        return status.get("status") == "healthy"
        
    async def get_metrics(self) -> Dict[str, Any]:
        """获取指标数据"""
        return {
            "agents": {
                "active": 10,
                "completed_tasks": 500,
                "failed_tasks": 5
            },
            "skills": {
                "registered": 50,
                "executions": 1000,
                "average_execution_time": 2.5
            },
            "memory": {
                "sessions": 100,
                "average_context_size": 1000
            }
        }
