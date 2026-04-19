"""
Audit Logger - 审计日志服务
"""

from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel
from enum import Enum


class AuditAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    LOGIN = "login"
    LOGOUT = "logout"


class AuditLog(BaseModel):
    """审计日志"""
    id: str
    tenant_id: str
    actor_id: str
    action: AuditAction
    resource_type: str
    resource_id: str
    result: str
    trace_id: Optional[str] = None
    run_id: Optional[str] = None
    details: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime = datetime.now()


class AuditLogger:
    """审计日志服务"""

    def __init__(self):
        self._logs: list[AuditLog] = []

    def log(
        self,
        tenant_id: str,
        actor_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        result: str,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """记录审计日志"""
        log_id = f"audit_{len(self._logs)}_{datetime.now().timestamp()}"

        audit_log = AuditLog(
            id=log_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            trace_id=trace_id,
            run_id=run_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._logs.append(audit_log)
        return audit_log

    def query(
        self,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        resource_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """查询审计日志"""
        logs = self._logs.copy()

        if tenant_id:
            logs = [l for l in logs if l.tenant_id == tenant_id]
        if actor_id:
            logs = [l for l in logs if l.actor_id == actor_id]
        if action:
            logs = [l for l in logs if l.action == action]
        if resource_type:
            logs = [l for l in logs if l.resource_type == resource_type]
        if start_time:
            logs = [l for l in logs if l.timestamp >= start_time]
        if end_time:
            logs = [l for l in logs if l.timestamp <= end_time]

        logs.sort(key=lambda x: x.timestamp, reverse=True)
        return logs[:limit]

    def get_logs_count(self, tenant_id: str) -> int:
        """获取租户日志数量"""
        return len([l for l in self._logs if l.tenant_id == tenant_id])


audit_logger = AuditLogger()