"""
Alerting API
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from management.alerting import AlertRule


router = APIRouter(prefix="/alerting", tags=["alerting"])

# 别名路由 - 支持 /api/alerts 和 /api/alerting/alerts 两种路径
alias_router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertRuleCreate(BaseModel):
    """创建告警规则"""
    name: str
    layer: str
    metric: str
    condition: str
    threshold: float
    duration: int
    severity: str


@router.get("/alerts")
async def get_alerts(request: Request, severity: Optional[str] = None) -> Dict[str, Any]:
    """获取告警列表
    
    Args:
        severity: 告警级别过滤 (info, warning, critical)
    
    Returns:
        告警列表
    """
    active_alerts: Dict[str, Any] = request.app.state.active_alerts
    alerts_list = list(active_alerts.values())
    
    if severity:
        alerts_list = [a for a in alerts_list if a.get("severity") == severity]
    
    return {
        "total": len(alerts_list),
        "alerts": alerts_list
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: Request) -> Dict[str, Any]:
    """确认告警
    
    Args:
        alert_id: 告警ID
    
    Returns:
        操作结果
    """
    active_alerts: Dict[str, Any] = request.app.state.active_alerts
    if alert_id not in active_alerts:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    
    active_alerts[alert_id]["status"] = "acknowledged"
    
    return {"status": "success", "message": f"Alert '{alert_id}' acknowledged"}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, request: Request) -> Dict[str, Any]:
    """解决告警
    
    Args:
        alert_id: 告警ID
    
    Returns:
        操作结果
    """
    active_alerts: Dict[str, Any] = request.app.state.active_alerts
    if alert_id not in active_alerts:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    
    active_alerts[alert_id]["status"] = "resolved"
    
    return {"status": "success", "message": f"Alert '{alert_id}' resolved"}


@router.get("/rules")
async def get_alert_rules(request: Request) -> Dict[str, Any]:
    """获取告警规则列表
    
    Returns:
        告警规则列表
    """
    alert_engine = request.app.state.alert_engine
    rules = [
        {
            "name": rule.name,
            "layer": rule.layer,
            "metric": rule.metric,
            "condition": rule.condition,
            "threshold": rule.threshold,
            "duration": rule.duration,
            "severity": rule.severity,
            "enabled": rule.enabled
        }
        for rule in alert_engine.rules
    ]
    
    return {
        "total": len(rules),
        "rules": rules
    }


@router.post("/rules")
async def create_alert_rule(rule: AlertRuleCreate, request: Request) -> Dict[str, Any]:
    """创建告警规则
    
    Args:
        rule: 告警规则
    
    Returns:
        创建结果
    """
    alert_engine = request.app.state.alert_engine
    new_rule = AlertRule(
        name=rule.name,
        layer=rule.layer,
        metric=rule.metric,
        condition=rule.condition,
        threshold=rule.threshold,
        duration=rule.duration,
        severity=rule.severity,
    )
    
    alert_engine.add_rule(new_rule)
    
    return {
        "status": "success",
        "message": f"Alert rule '{rule.name}' created",
        "rule": {
            "name": rule.name,
            "layer": rule.layer,
            "metric": rule.metric,
            "condition": rule.condition,
            "threshold": rule.threshold,
            "duration": rule.duration,
            "severity": rule.severity
        }
    }


@router.delete("/rules/{rule_name}")
async def delete_alert_rule(rule_name: str, request: Request) -> Dict[str, Any]:
    """删除告警规则
    
    Args:
        rule_name: 规则名称
    
    Returns:
        删除结果
    """
    request.app.state.alert_engine.remove_rule(rule_name)
    
    return {"status": "success", "message": f"Alert rule '{rule_name}' deleted"}


# ===== 别名路由 - 支持 /api/alerts =====

@alias_router.get("")
async def get_alerts_alias(request: Request, severity: Optional[str] = None) -> Dict[str, Any]:
    """获取告警列表（别名路由）"""
    return await get_alerts(request, severity)


@alias_router.post("/{alert_id}/acknowledge")
async def acknowledge_alert_alias(alert_id: str, request: Request) -> Dict[str, Any]:
    """确认告警（别名路由）"""
    return await acknowledge_alert(alert_id, request)


@alias_router.post("/{alert_id}/resolve")
async def resolve_alert_alias(alert_id: str, request: Request) -> Dict[str, Any]:
    """解决告警（别名路由）"""
    return await resolve_alert(alert_id, request)
