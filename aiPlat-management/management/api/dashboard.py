"""
Dashboard API
"""

from fastapi import APIRouter, Request, HTTPException


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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
async def get_status(request: Request):
    """获取各层状态"""
    status = await request.app.state.aggregator.aggregate()
    return status


@router.get("/health")
async def get_health(request: Request):
    """获取健康检查结果"""
    health = await request.app.state.aggregator.get_health()
    return health


@router.get("/metrics")
async def get_metrics(request: Request):
    """获取所有层级指标"""
    metrics = await request.app.state.aggregator.get_metrics()
    return metrics


# ===== 配置管理 API (与文档对齐) =====

@router.get("/config")
@router.get("/config/")
async def get_all_configs(request: Request):
    """获取所有组件配置"""
    client = getattr(request.app.state, "infra_client", None)
    if not client:
        raise HTTPException(status_code=503, detail="Infra client not initialized")
    payload = await client.list_managers()
    if isinstance(payload, dict) and payload.get("status") == "success":
        return {"managers": payload.get("data", [])}
    return payload


@router.get("/config/{component}")
async def get_component_config(component: str, request: Request):
    """获取指定组件配置"""
    client = getattr(request.app.state, "infra_client", None)
    if not client:
        raise HTTPException(status_code=503, detail="Infra client not initialized")
    return await client.get_manager_config(component)


@router.put("/config/{component}")
async def update_component_config(component: str, config: dict, request: Request):
    """更新指定组件配置"""
    client = getattr(request.app.state, "infra_client", None)
    if not client:
        raise HTTPException(status_code=503, detail="Infra client not initialized")
    return await client.update_manager_config(component, config)
