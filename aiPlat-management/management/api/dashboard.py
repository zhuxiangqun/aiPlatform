"""
Dashboard API
"""

from fastapi import APIRouter
from ..dashboard import DashboardAggregator, InfraAdapter, CoreAdapter, PlatformAdapter, AppAdapter


router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# 创建聚合器
aggregator = DashboardAggregator()
aggregator.register_adapter("infra", InfraAdapter())
aggregator.register_adapter("core", CoreAdapter())
aggregator.register_adapter("platform", PlatformAdapter())
aggregator.register_adapter("app", AppAdapter())


@router.get("")
@router.get("/")
async def dashboard_root():
    """Dashboard API 总览"""
    return {
        "name": "Dashboard API",
        "description": "四层架构状态聚合和总览",
        "endpoints": {
            "status": {
                "path": "/api/dashboard/status",
                "method": "GET",
                "description": "获取各层状态"
            },
            "health": {
                "path": "/api/dashboard/health",
                "method": "GET",
                "description": "获取健康检查结果"
            },
            "metrics": {
                "path": "/api/dashboard/metrics",
                "method": "GET",
                "description": "获取所有层级指标"
            }
        }
    }


@router.get("/status")
async def get_status():
    """获取各层状态"""
    status = await aggregator.aggregate()
    return status


@router.get("/health")
async def get_health():
    """获取健康检查结果"""
    health = await aggregator.get_health()
    return health


@router.get("/metrics")
async def get_metrics():
    """获取所有层级指标"""
    metrics = await aggregator.get_metrics()
    return metrics


# ===== 配置管理 API (与文档对齐) =====

@router.get("/config")
@router.get("/config/")
async def get_all_configs():
    """获取所有组件配置"""
    infra_adapter = aggregator.adapters.get("infra")
    if infra_adapter:
        return await infra_adapter.get_all_configs()
    return {}


@router.get("/config/{component}")
async def get_component_config(component: str):
    """获取指定组件配置"""
    infra_adapter = aggregator.adapters.get("infra")
    if infra_adapter:
        return await infra_adapter.get_config(component)
    return {}


@router.put("/config/{component}")
async def update_component_config(component: str, config: dict):
    """更新指定组件配置"""
    infra_adapter = aggregator.adapters.get("infra")
    if infra_adapter:
        return await infra_adapter.update_config(component, config)
    return {"error": "Component not found"}
