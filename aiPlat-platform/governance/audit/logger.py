"""
Audit Logger - 审计日志服务

Tamper-proof audit trail with SHA-256 hash chaining.
Each log entry references the hash of the previous entry,
forming an immutable chain verifiable via verify_integrity().
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
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
    timestamp: datetime = datetime.now(timezone.utc)
    # ── Tamper-proof chain ──
    prev_hash: Optional[str] = None
    entry_hash: Optional[str] = None


class AuditLogger:
    """审计日志服务 — SHA-256 链式哈希防篡改"""

    def __init__(self):
        self._logs: list[AuditLog] = []
        self._prev_hash: Optional[str] = None

    def _compute_hash(self, entry_data: Dict[str, Any]) -> str:
        raw = json.dumps(entry_data, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

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
        """记录审计日志（含链式哈希）"""
        log_id = f"audit_{len(self._logs)}_{datetime.now(timezone.utc).timestamp()}"

        # Build entry with prev_hash for chain integrity
        entry_data = {
            "id": log_id, "tenant_id": tenant_id, "actor_id": actor_id,
            "action": action, "resource_type": resource_type,
            "resource_id": resource_id, "result": result,
            "prev_hash": self._prev_hash or "",
        }
        entry_hash = self._compute_hash(entry_data)
        self._prev_hash = entry_hash

        audit_log = AuditLog(
            id=log_id, tenant_id=tenant_id, actor_id=actor_id,
            action=action, resource_type=resource_type,
            resource_id=resource_id, result=result,
            trace_id=trace_id, run_id=run_id,
            details=details or {}, ip_address=ip_address,
            user_agent=user_agent,
            prev_hash=entry_data["prev_hash"] or None,
            entry_hash=entry_hash,
        )
        self._logs.append(audit_log)
        return audit_log

    def verify_integrity(self) -> List[Dict[str, Any]]:
        """验证审计日志链完整性。返回篡改位置的列表。"""
        violations = []
        expected_hash: Optional[str] = None
        for i, log in enumerate(self._logs):
            entry_data = {
                "id": log.id, "tenant_id": log.tenant_id,
                "actor_id": log.actor_id, "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id, "result": log.result,
                "prev_hash": log.prev_hash or "",
            }
            computed = self._compute_hash(entry_data)
            if computed != (log.entry_hash or ""):
                violations.append({
                    "index": i, "log_id": log.id,
                    "expected_hash": computed,
                    "stored_hash": log.entry_hash,
                    "error": "hash_mismatch",
                })
            if i > 0 and self._logs[i - 1].entry_hash != log.prev_hash:
                violations.append({
                    "index": i, "log_id": log.id,
                    "expected_prev": self._logs[i - 1].entry_hash,
                    "stored_prev": log.prev_hash,
                    "error": "chain_broken",
                })
        return violations

    def get_today_count(self, tenant_id: str = None) -> int:
        """获取今日审计日志数量"""
        today = datetime.now(timezone.utc).date()
        logs = self._logs
        if tenant_id:
            logs = [l for l in logs if l.tenant_id == tenant_id]
        return sum(1 for l in logs if l.timestamp.date() == today)

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