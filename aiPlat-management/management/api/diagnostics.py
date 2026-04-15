"""
Diagnostics API
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from management.diagnostics import (
    InfraHealthChecker,
    CoreHealthChecker,
    PlatformHealthChecker,
    AppHealthChecker,
)


router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

# 创建健康检查器
health_checkers = {
    "infra": InfraHealthChecker(),
    "core": CoreHealthChecker(),
    "platform": PlatformHealthChecker(),
    "app": AppHealthChecker(),
}


@router.get("/health/{layer}")
async def get_layer_health(layer: str) -> Dict[str, Any]:
    """获取指定层级健康状态
    
    Args:
        layer: 层级名称 (infra, core, platform, app)
    
    Returns:
        健康状态
    """
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")
    
    checker = health_checkers[layer]
    health = await checker.get_health()
    
    return health


@router.get("/health/all")
async def get_all_health() -> Dict[str, Dict[str, Any]]:
    """获取所有层级健康状态
    
    Returns:
        所有层级的健康状态
    """
    all_health = {}
    
    for layer, checker in health_checkers.items():
        health = await checker.get_health()
        all_health[layer] = health
    
    return all_health


@router.get("/health")
async def list_available_checks() -> Dict[str, Any]:
    """列出可用的健康检查
    
    Returns:
        可用的健康检查列表
    """
    return {
        "layers": list(health_checkers.keys()),
        "description": {
            "infra": "Infrastructure layer health checks",
            "core": "Core AI layer health checks",
            "platform": "Platform services health checks",
            "app": "Application layer health checks"
        }
    }


@router.post("/check/{layer}")
async def run_layer_diagnosis(layer: str) -> Dict[str, Any]:
    """运行层级诊断
    
    Args:
        layer: 层级名称 (infra, core, platform, app)
    
    Returns:
        诊断结果
    """
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")
    
    checker = health_checkers[layer]
    results = await checker.check()
    
    # 统计状态
    status_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0}
    for result in results:
        status_counts[result.status.value] += 1
    
    # 整体状态
    if status_counts["unhealthy"] > 0:
        overall_status = "unhealthy"
    elif status_counts["degraded"] > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    return {
        "layer": layer,
        "overall_status": overall_status,
        "status_counts": status_counts,
        "checks": [
            {
                "component": r.component,
                "status": r.status.value,
                "message": r.message,
                "details": r.details
            }
            for r in results
        ]
    }


@router.get("/trace/{layer}")
async def get_layer_trace(layer: str) -> Dict[str, Any]:
    """获取层级链路追踪
    
    Args:
        layer: 层级名称 (infra, core, platform, app)
    
    Returns:
        链路追踪数据
    """
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")
    
    # TODO: 实现链路追踪
    return {
        "layer": layer,
        "traces": [],
        "message": "Tracing not implemented yet"
    }


@router.get("/system")
async def get_system_overview() -> Dict[str, Any]:
    """获取系统概览
    
    Returns:
        系统概览
    """
    overview = {
        "overall_status": "healthy",
        "layers": {},
        "summary": {
            "total_layers": 4,
            "healthy_layers": 0,
            "degraded_layers": 0,
            "unhealthy_layers": 0
        }
    }
    
    for layer, checker in health_checkers.items():
        health = await checker.get_health()
        overview["layers"][layer] = health
        
        if health["status"] == "healthy":
            overview["summary"]["healthy_layers"] += 1
        elif health["status"] == "degraded":
            overview["summary"]["degraded_layers"] += 1
            overview["overall_status"] = "degraded"
        elif health["status"] == "unhealthy":
            overview["summary"]["unhealthy_layers"] += 1
            overview["overall_status"] = "unhealthy"
    
    return overview