"""
告警规则引擎
"""

from typing import Dict, Any, List, Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    layer: str
    metric: str
    condition: str  # >, <, >=, <=, ==, !=
    threshold: float
    duration: int  # 持续时间（秒）
    severity: str  # info, warning, critical
    enabled: bool = True
    

class AlertEngine:
    """告警引擎"""
    
    def __init__(self):
        self.rules: List[AlertRule] = []
        self.active_alerts: Dict[str, Any] = {}
        
    def add_rule(self, rule: AlertRule):
        """添加告警规则"""
        self.rules.append(rule)
        
    def remove_rule(self, rule_name: str):
        """移除告警规则"""
        self.rules = [r for r in self.rules if r.name != rule_name]
        
    async def evaluate(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """评估告警规则"""
        triggered_alerts = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
                
            # 获取指标值
            layer_metrics = metrics.get(rule.layer, {})
            metric_value = layer_metrics.get(rule.metric, {}).get("value", 0)
            
            # 评估条件
            condition_met = self._evaluate_condition(
                metric_value, 
                rule.condition, 
                rule.threshold
            )
            
            if condition_met:
                alert = {
                    "rule": rule.name,
                    "layer": rule.layer,
                    "metric": rule.metric,
                    "value": metric_value,
                    "threshold": rule.threshold,
                    "severity": rule.severity,
                    "timestamp": datetime.utcnow().isoformat()
                }
                triggered_alerts.append(alert)
                
        return triggered_alerts
        
    def _evaluate_condition(
        self, 
        value: float, 
        condition: str, 
        threshold: float
    ) -> bool:
        """评估条件"""
        operators = {
            ">": lambda v, t: v > t,
            "<": lambda v, t: v < t,
            ">=": lambda v, t: v >= t,
            "<=": lambda v, t: v <= t,
            "==": lambda v, t: v == t,
            "!=": lambda v, t: v != t
        }
        
        operator = operators.get(condition)
        if operator:
            return operator(value, threshold)
        return False
