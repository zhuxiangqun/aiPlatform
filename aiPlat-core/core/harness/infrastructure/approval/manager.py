"""
Approval Manager

Manages approval rules and requests for the Human-in-the-Loop system.
Based on framework/patterns.md §7.
"""

from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import uuid
import sqlite3
import json

from .types import (
    RuleType,
    RequestStatus,
    ApprovalRule,
    ApprovalRequest,
    ApprovalResult,
    ApprovalContext,
)


class ApprovalValidationError(Exception):
    """Exception raised for approval validation errors."""
    pass


class ApprovalManager:
    """
    Approval Manager - Core component of Human-in-the-Loop system.
    
    Features:
    - Rule registration and management
    - Automatic approval condition evaluation
    - Request lifecycle management
    - Approval/rejection workflow
    - First-time operation tracking
    - Statistics and reporting
    """

    def __init__(self, execution_store: Optional[Any] = None):
        self._rules: Dict[str, ApprovalRule] = {}
        self._requests: Dict[str, ApprovalRequest] = {}
        self._operation_history: Dict[str, Dict[str, int]] = {}  # user_id -> {operation -> count}
        self._callbacks: Dict[str, List[Callable]] = {
            "on_request_created": [],
            "on_approved": [],
            "on_rejected": [],
            "on_expired": [],
            "on_auto_approved": [],
        }
        self._execution_store = execution_store

    def _db_path(self) -> Optional[str]:
        if not self._execution_store:
            return None
        # Best effort: ExecutionStore keeps config on _config.db_path
        cfg = getattr(self._execution_store, "_config", None)
        if cfg and getattr(cfg, "db_path", None):
            return str(cfg.db_path)
        return getattr(self._execution_store, "db_path", None)

    def _sync_load_request_from_store(self, request_id: str) -> Optional[Dict[str, Any]]:
        db_path = self._db_path()
        if not db_path:
            return None
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM approval_requests WHERE request_id=?",
                    (request_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "request_id": row["request_id"],
                    "user_id": row["user_id"],
                    "operation": row["operation"],
                    "details": row["details"],
                    "rule_id": row["rule_id"],
                    "rule_type": row["rule_type"],
                    "status": row["status"],
                    "amount": row["amount"],
                    "batch_size": row["batch_size"],
                    "is_first_time": bool(row["is_first_time"] or 0),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "expires_at": row["expires_at"],
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                    "result": json.loads(row["result_json"] or "null"),
                }
            finally:
                conn.close()
        except Exception:
            return None

    def _sync_list_pending_from_store(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        db_path = self._db_path()
        if not db_path:
            return []
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                if user_id:
                    rows = conn.execute(
                        """
                        SELECT * FROM approval_requests
                        WHERE status=? AND user_id=?
                        ORDER BY created_at ASC
                        """,
                        (RequestStatus.PENDING.value, user_id),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT * FROM approval_requests
                        WHERE status=?
                        ORDER BY created_at ASC
                        """,
                        (RequestStatus.PENDING.value,),
                    ).fetchall()
                out: List[Dict[str, Any]] = []
                for row in rows:
                    out.append(
                        {
                            "request_id": row["request_id"],
                            "user_id": row["user_id"],
                            "operation": row["operation"],
                            "details": row["details"],
                            "rule_id": row["rule_id"],
                            "rule_type": row["rule_type"],
                            "status": row["status"],
                            "amount": row["amount"],
                            "batch_size": row["batch_size"],
                            "is_first_time": bool(row["is_first_time"] or 0),
                            "created_at": row["created_at"],
                            "updated_at": row["updated_at"],
                            "expires_at": row["expires_at"],
                            "metadata": json.loads(row["metadata_json"] or "{}"),
                            "result": json.loads(row["result_json"] or "null"),
                        }
                    )
                return out
            finally:
                conn.close()
        except Exception:
            return []

    def _to_record(self, req: ApprovalRequest) -> Dict[str, Any]:
        return {
            "request_id": req.request_id,
            "user_id": req.user_id,
            "operation": req.operation,
            "details": req.details,
            "rule_id": req.rule_id,
            "rule_type": req.rule_type.value if req.rule_type else None,
            "status": req.status.value,
            "amount": req.amount,
            "batch_size": req.batch_size,
            "is_first_time": req.is_first_time,
            "created_at": req.created_at.timestamp(),
            "updated_at": req.updated_at.timestamp(),
            "expires_at": req.expires_at.timestamp() if req.expires_at else None,
            "metadata": req.metadata or {},
            "result": {
                "request_id": req.result.request_id,
                "decision": req.result.decision.value,
                "comments": req.result.comments,
                "approved_by": req.result.approved_by,
                "timestamp": req.result.timestamp.timestamp(),
                "metadata": req.result.metadata or {},
            } if req.result else None,
        }

    def _from_record(self, rec: Dict[str, Any]) -> ApprovalRequest:
        from .types import RuleType, RequestStatus
        from datetime import datetime

        rule_type = None
        if rec.get("rule_type"):
            try:
                rule_type = RuleType(rec["rule_type"])
            except Exception:
                rule_type = None
        status = RequestStatus(rec.get("status") or RequestStatus.PENDING.value)
        req = ApprovalRequest(
            request_id=rec["request_id"],
            user_id=rec.get("user_id") or "",
            operation=rec.get("operation") or "",
            details=rec.get("details") or "",
            rule_id=rec.get("rule_id"),
            rule_type=rule_type,
            status=status,
            amount=rec.get("amount"),
            batch_size=rec.get("batch_size"),
            is_first_time=bool(rec.get("is_first_time") or False),
            created_at=datetime.utcfromtimestamp(float(rec.get("created_at") or datetime.utcnow().timestamp())),
            updated_at=datetime.utcfromtimestamp(float(rec.get("updated_at") or datetime.utcnow().timestamp())),
            expires_at=datetime.utcfromtimestamp(float(rec["expires_at"])) if rec.get("expires_at") else None,
            metadata=rec.get("metadata") or {},
        )
        res = rec.get("result")
        if isinstance(res, dict):
            try:
                req.result = ApprovalResult(
                    request_id=req.request_id,
                    decision=RequestStatus(res.get("decision") or RequestStatus.APPROVED.value),
                    comments=res.get("comments") or "",
                    approved_by=res.get("approved_by"),
                    timestamp=datetime.utcfromtimestamp(float(res.get("timestamp") or datetime.utcnow().timestamp())),
                    metadata=res.get("metadata") or {},
                )
            except Exception:
                pass
        return req

    async def _persist(self, req: ApprovalRequest) -> None:
        if not self._execution_store:
            return
        try:
            await self._execution_store.upsert_approval_request(self._to_record(req))
        except Exception:
            return

    def register_rule(self, rule: ApprovalRule) -> str:
        """
        Register an approval rule.
        
        Args:
            rule: Approval rule to register
            
        Returns:
            Rule ID
        """
        self._rules[rule.rule_id] = rule
        return rule.rule_id

    def unregister_rule(self, rule_id: str) -> bool:
        """
        Unregister an approval rule.
        
        Args:
            rule_id: Rule ID to unregister
            
        Returns:
            True if rule was removed
        """
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[ApprovalRule]:
        """Get a rule by ID."""
        return self._rules.get(rule_id)

    def list_rules(
        self,
        rule_type: Optional[RuleType] = None,
        enabled_only: bool = False
    ) -> List[ApprovalRule]:
        """
        List approval rules.
        
        Args:
            rule_type: Filter by rule type (optional)
            enabled_only: Only return enabled rules
            
        Returns:
            List of approval rules
        """
        rules = list(self._rules.values())
        
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        
        return sorted(rules, key=lambda r: r.priority)

    def check_approval_required(self, context: ApprovalContext) -> Optional[ApprovalRule]:
        """
        Check if an operation requires approval.
        
        Evaluates all enabled rules against the context.
        Returns the first matching rule (highest priority) or None.
        
        Args:
            context: Approval context to evaluate
            
        Returns:
            Matching ApprovalRule or None if no approval required
        """
        self._update_first_time_flag(context)
        
        matching_rules = []
        
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            if rule.matches(context):
                matching_rules.append(rule)
        
        if not matching_rules:
            return None
        
        matching_rules.sort(key=lambda r: r.priority)
        return matching_rules[0]

    def create_request(
        self,
        context: ApprovalContext,
        rule: Optional[ApprovalRule] = None
    ) -> ApprovalRequest:
        """
        Create an approval request.
        
        Args:
            context: Approval context
            rule: Matching rule (if None, auto-detect)
            
        Returns:
            Created ApprovalRequest
        """
        if rule is None:
            rule = self.check_approval_required(context)
        
        if rule is None:
            request = ApprovalRequest(
                request_id=str(uuid.uuid4()),
                user_id=context.user_id,
                operation=context.operation,
                details=context.details if hasattr(context, 'details') else "",
                status=RequestStatus.AUTO_APPROVED,
                amount=context.amount,
                batch_size=context.batch_size,
                is_first_time=context.is_first_time,
                metadata=context.metadata
            )
            request.result = ApprovalResult(
                request_id=request.request_id,
                decision=RequestStatus.AUTO_APPROVED,
                comments="No approval rule matched - auto-approved",
                approved_by="system"
            )
            self._requests[request.request_id] = request
            self._notify_callbacks("on_auto_approved", request)
            try:
                # fire-and-forget persistence
                import asyncio
                asyncio.create_task(self._persist(request))
            except Exception:
                pass
            return request
        
        expires_at = None
        if rule.expires_in_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=rule.expires_in_seconds)
        
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            user_id=context.user_id,
            operation=context.operation,
            details=context.details if hasattr(context, 'details') else "",
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            amount=context.amount,
            batch_size=context.batch_size,
            is_first_time=context.is_first_time,
            expires_at=expires_at,
            metadata=context.metadata
        )
        
        self._requests[request.request_id] = request
        self._update_operation_history(context)
        self._notify_callbacks("on_request_created", request)
        try:
            import asyncio
            asyncio.create_task(self._persist(request))
        except Exception:
            pass
        
        return request

    async def approve(
        self,
        request_id: str,
        approved_by: str,
        comments: str = ""
    ) -> Optional[ApprovalRequest]:
        """
        Approve a pending request.
        
        Args:
            request_id: Request ID to approve
            approved_by: Who approved it
            comments: Approval comments
            
        Returns:
            Updated ApprovalRequest or None if not found
        """
        request = self._requests.get(request_id)
        if not request:
            return None
        
        if not request.is_resolved() and request.status == RequestStatus.PENDING:
            request.status = RequestStatus.APPROVED
            request.updated_at = datetime.utcnow()
            request.result = ApprovalResult(
                request_id=request_id,
                decision=RequestStatus.APPROVED,
                comments=comments,
                approved_by=approved_by
            )
            self._notify_callbacks("on_approved", request)
            await self._persist(request)
        
        return request

    async def reject(
        self,
        request_id: str,
        rejected_by: str,
        comments: str = ""
    ) -> Optional[ApprovalRequest]:
        """
        Reject a pending request.
        
        Args:
            request_id: Request ID to reject
            rejected_by: Who rejected it
            comments: Rejection comments
            
        Returns:
            Updated ApprovalRequest or None if not found
        """
        request = self._requests.get(request_id)
        if not request:
            return None
        
        if not request.is_resolved() and request.status == RequestStatus.PENDING:
            request.status = RequestStatus.REJECTED
            request.updated_at = datetime.utcnow()
            request.result = ApprovalResult(
                request_id=request_id,
                decision=RequestStatus.REJECTED,
                comments=comments,
                approved_by=rejected_by
            )
            self._notify_callbacks("on_rejected", request)
            await self._persist(request)
        
        return request

    async def cancel_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """
        Cancel a pending request.
        
        Args:
            request_id: Request ID to cancel
            
        Returns:
            Updated ApprovalRequest or None if not found
        """
        request = self._requests.get(request_id)
        if not request:
            return None
        
        if not request.is_resolved() and request.status == RequestStatus.PENDING:
            request.status = RequestStatus.CANCELLED
            request.updated_at = datetime.utcnow()
            await self._persist(request)
        
        return request

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a request by ID."""
        request = self._requests.get(request_id)
        if request is None and self._execution_store:
            rec = self._sync_load_request_from_store(request_id)
            if rec:
                try:
                    request = self._from_record(rec)
                    self._requests[request.request_id] = request
                except Exception:
                    request = None
        if request and request.is_expired() and request.status == RequestStatus.PENDING:
            request.status = RequestStatus.EXPIRED
            request.updated_at = datetime.utcnow()
            self._notify_callbacks("on_expired", request)
        return request

    def get_pending_requests(
        self,
        user_id: Optional[str] = None,
        rule_type: Optional[RuleType] = None
    ) -> List[ApprovalRequest]:
        """
        Get pending approval requests.
        
        Args:
            user_id: Filter by user (optional)
            rule_type: Filter by rule type (optional)
            
        Returns:
            List of pending requests
        """
        # Prefer store-backed listing when available (survives restarts).
        if self._execution_store:
            items: List[ApprovalRequest] = []
            for rec in self._sync_list_pending_from_store(user_id=user_id):
                try:
                    items.append(self._from_record(rec))
                except Exception:
                    continue
            if rule_type:
                items = [r for r in items if r.rule_type == rule_type]
            return sorted(items, key=lambda r: r.created_at)

        requests = [r for r in self._requests.values() if r.status == RequestStatus.PENDING]
        
        if user_id:
            requests = [r for r in requests if r.user_id == user_id]
        
        if rule_type:
            requests = [r for r in requests if r.rule_type == rule_type]
        
        return sorted(requests, key=lambda r: r.created_at)

    def auto_approve(
        self,
        request_id: str,
        reason: str = "Auto-approved by system"
    ) -> Optional[ApprovalRequest]:
        """
        Auto-approve a request (for when conditions allow automatic processing).
        
        Args:
            request_id: Request ID
            reason: Auto-approval reason
            
        Returns:
            Updated ApprovalRequest or None
        """
        request = self._requests.get(request_id)
        if not request:
            return None
        
        if not request.is_resolved() and request.status == RequestStatus.PENDING:
            request.status = RequestStatus.AUTO_APPROVED
            request.updated_at = datetime.utcnow()
            request.result = ApprovalResult(
                request_id=request_id,
                decision=RequestStatus.AUTO_APPROVED,
                comments=reason,
                approved_by="system"
            )
            self._notify_callbacks("on_auto_approved", request)
        
        return request

    def check_and_request(
        self,
        context: ApprovalContext
    ) -> ApprovalRequest:
        """
        Check if approval is needed and create a request if so.
        
        This is the main entry point for the approval workflow:
        1. Evaluate rules against context
        2. If no rule matches, auto-approve
        3. If rule matches with auto_approve=True, auto-approve
        4. Otherwise, create a pending request for human review
        
        Args:
            context: Approval context
            
        Returns:
            ApprovalRequest (may be auto-approved or pending)
        """
        rule = self.check_approval_required(context)
        
        request = self.create_request(context, rule)
        
        if rule and rule.auto_approve and request.status == RequestStatus.PENDING:
            return self.auto_approve(
                request.request_id,
                f"Auto-approved by rule: {rule.name}"
            )
        
        return request

    async def wait_for_approval(
        self,
        request_id: str,
        timeout_seconds: int = 300
    ) -> ApprovalResult:
        """
        Wait for approval decision (simplified — in production, use async/event).
        
        Args:
            request_id: Request ID to wait for
            timeout_seconds: Maximum wait time
            
        Returns:
            ApprovalResult
            
        Raises:
            ApprovalValidationError: If request not found or timed out
        """
        import asyncio
        
        start_time = datetime.utcnow()
        timeout = timedelta(seconds=timeout_seconds)
        
        while True:
            request = self._requests.get(request_id)
            if not request:
                raise ApprovalValidationError(f"Request not found: {request_id}")
            
            if request.is_resolved():
                return request.result
            
            if datetime.utcnow() - start_time > timeout:
                request.status = RequestStatus.EXPIRED
                request.updated_at = datetime.utcnow()
                request.result = ApprovalResult(
                    request_id=request_id,
                    decision=RequestStatus.EXPIRED,
                    comments=f"Request timed out after {timeout_seconds} seconds"
                )
                self._notify_callbacks("on_expired", request)
                return request.result
            
            await asyncio.sleep(1)

    def register_callback(self, event: str, callback: Callable) -> None:
        """
        Register a callback for approval events.
        
        Args:
            event: Event name (on_request_created, on_approved, on_rejected, on_expired, on_auto_approved)
            callback: Callback function(request: ApprovalRequest)
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def get_stats(self) -> Dict[str, Any]:
        """Get approval statistics."""
        total = len(self._requests)
        by_status = {}
        
        for status in RequestStatus:
            by_status[status.value] = sum(
                1 for r in self._requests.values() if r.status == status
            )
        
        by_rule_type = {}
        for rule_type in RuleType:
            by_rule_type[rule_type.value] = sum(
                1 for r in self._requests.values() if r.rule_type == rule_type
            )
        
        avg_response_time = 0.0
        resolved = [
            r for r in self._requests.values()
            if r.is_resolved() and r.result is not None
        ]
        if resolved:
            times = [
                (r.result.timestamp - r.created_at).total_seconds()
                for r in resolved
            ]
            avg_response_time = sum(times) / len(times)
        
        return {
            "total_requests": total,
            "by_status": by_status,
            "by_rule_type": by_rule_type,
            "avg_response_time_seconds": avg_response_time,
            "active_rules": sum(1 for r in self._rules.values() if r.enabled),
            "total_rules": len(self._rules)
        }

    def _update_first_time_flag(self, context: ApprovalContext) -> None:
        """Update is_first_time flag based on operation history."""
        if context.user_id and context.operation:
            if context.user_id not in self._operation_history:
                context.is_first_time = True
            elif context.operation not in self._operation_history.get(context.user_id, {}):
                context.is_first_time = True
            else:
                context.is_first_time = False

    def _update_operation_history(self, context: ApprovalContext) -> None:
        """Track operation history for first-time detection."""
        if context.user_id and context.operation:
            if context.user_id not in self._operation_history:
                self._operation_history[context.user_id] = {}
            
            user_ops = self._operation_history[context.user_id]
            user_ops[context.operation] = user_ops.get(context.operation, 0) + 1

    def _notify_callbacks(self, event: str, request: ApprovalRequest) -> None:
        """Notify registered callbacks of an event."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(request)
            except Exception:
                pass


def create_approval_manager(
    default_rules: bool = True
) -> ApprovalManager:
    """
    Create an ApprovalManager with default rules.
    
    Args:
        default_rules: Whether to include default rules
        
    Returns:
        Configured ApprovalManager
    """
    manager = ApprovalManager()
    
    if default_rules:
        manager.register_rule(ApprovalRule(
            rule_id="default_amount_threshold",
            rule_type=RuleType.AMOUNT_THRESHOLD,
            name="金额阈值审批",
            description="金额超过阈值时需要人工审批",
            threshold=10000.0,
            priority=10,
            metadata={"currency": "CNY"}
        ))
        
        manager.register_rule(ApprovalRule(
            rule_id="default_sensitive_operation",
            rule_type=RuleType.SENSITIVE_OPERATION,
            name="敏感操作审批",
            description="涉及敏感数据和权限的操作需要人工审批",
            priority=5,
            metadata={"sensitive_operations": [
                "delete_data", "modify_permissions", "export_data",
                "change_config", "reset_system"
            ]}
        ))
        
        manager.register_rule(ApprovalRule(
            rule_id="default_batch_operation",
            rule_type=RuleType.BATCH_OPERATION,
            name="批量操作审批",
            description="批量删除、修改操作需要人工审批",
            threshold=10,
            priority=20,
            metadata={}
        ))
        
        manager.register_rule(ApprovalRule(
            rule_id="default_first_time",
            rule_type=RuleType.FIRST_TIME,
            name="首次操作审批",
            description="首次执行某类操作需要人工审批",
            auto_approve=False,
            priority=30,
            metadata={}
        ))
    
    return manager
