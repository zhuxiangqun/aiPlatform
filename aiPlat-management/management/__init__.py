"""
aiPlat-management - AI Platform Management System

独立的管理系统，横切四层业务架构，提供：
- Dashboard: 四层总览和健康状态
- Monitoring: 指标采集和监控
- Alerting: 告警规则和通知
- Diagnostics: 健康检查和诊断
- Config: 配置管理和版本控制
"""

__version__ = "0.1.0"
__all__ = [
    "dashboard",
    "monitoring",
    "alerting",
    "diagnostics",
    "config",
    "api",
]