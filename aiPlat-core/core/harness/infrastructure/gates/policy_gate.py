"""
PolicyGate (Phase 3 - minimal).

Enforces:
- Permission checks (RBAC) via PermissionManager
- Best-effort approval checks via ApprovalManager (when present)

Design goal:
All tool syscalls must pass through PolicyGate in future phases.
In Phase 3 we make it opt-in for approval to avoid double-approval while
existing loops still do their own approval checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional
import os
import sqlite3
import json

from core.apps.tools.permission import get_permission_manager, Permission
from core.harness.kernel.runtime import get_kernel_runtime


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


@dataclass
class PolicyResult:
    decision: PolicyDecision
    reason: Optional[str] = None
    approval_request_id: Optional[str] = None


class PolicyGate:
    def __init__(self) -> None:
        # Default: do NOT enforce approval in syscall yet to avoid double approval.
        # Phase 4+: we will move approval fully into sys_tool and remove loop-level checks.
        self._enforce_approval = os.getenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false").lower() in (
            "1",
            "true",
            "yes",
            "y",
        )

    def check_tool(self, *, user_id: str, tool_name: str, tool_args: Optional[Dict[str, Any]] = None) -> PolicyResult:
        perm_mgr = get_permission_manager()
        if not perm_mgr.check_permission(user_id, tool_name, Permission.EXECUTE):
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason=f"User '{user_id}' lacks EXECUTE permission for tool '{tool_name}'",
            )

        # Tenant policy (policy-as-code): deny/approval_required tool lists.
        tenant_id = (tool_args or {}).get("_tenant_id") if isinstance(tool_args, dict) else None
        deny_by_policy = False
        require_approval_by_policy = False
        policy_reason = None
        if tenant_id:
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                db_path = getattr(getattr(store, "_config", None), "db_path", None)
                if db_path:
                    conn = sqlite3.connect(str(db_path))
                    try:
                        row = conn.execute(
                            "SELECT policy_json, version FROM tenant_policies WHERE tenant_id=? LIMIT 1", (str(tenant_id),)
                        ).fetchone()
                    finally:
                        conn.close()
                    if row and row[0]:
                        policy = json.loads(row[0]) if isinstance(row[0], str) else {}
                        tool_policy = policy.get("tool_policy") if isinstance(policy, dict) else None
                        if isinstance(tool_policy, dict):
                            deny_tools = tool_policy.get("deny_tools") if isinstance(tool_policy.get("deny_tools"), list) else []
                            approval_tools = (
                                tool_policy.get("approval_required_tools")
                                if isinstance(tool_policy.get("approval_required_tools"), list)
                                else []
                            )
                            if tool_name in deny_tools:
                                deny_by_policy = True
                                policy_reason = f"Denied by tenant policy (tenant_id={tenant_id})"
                            if tool_name in approval_tools:
                                require_approval_by_policy = True
            except Exception:
                # Fail-open for compatibility.
                pass

        if deny_by_policy:
            return PolicyResult(decision=PolicyDecision.DENY, reason=policy_reason or "Denied by tenant policy")

        force_approval = bool((tool_args or {}).get("_approval_required")) if isinstance(tool_args, dict) else False
        if require_approval_by_policy:
            force_approval = True

        if not self._enforce_approval and not force_approval:
            return PolicyResult(decision=PolicyDecision.ALLOW)

        runtime = get_kernel_runtime()
        approval_mgr = getattr(runtime, "approval_manager", None) if runtime else None
        if not approval_mgr:
            return PolicyResult(decision=PolicyDecision.ALLOW)

        # If caller provides an approval_request_id, honor it (resume semantics).
        approval_request_id = (tool_args or {}).get("_approval_request_id") if isinstance(tool_args, dict) else None
        if approval_request_id:
            try:
                req = approval_mgr.get_request(str(approval_request_id))
                if not req:
                    return PolicyResult(
                        decision=PolicyDecision.APPROVAL_REQUIRED,
                        reason=f"Approval request not found: {approval_request_id}",
                        approval_request_id=str(approval_request_id),
                    )
                status = getattr(req, "status", None)
                # Approved / auto-approved -> allow
                from core.harness.infrastructure.approval.types import RequestStatus

                if status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
                    return PolicyResult(decision=PolicyDecision.ALLOW)
                if status == RequestStatus.PENDING:
                    return PolicyResult(
                        decision=PolicyDecision.APPROVAL_REQUIRED,
                        reason=f"Tool '{tool_name}' requires approval",
                        approval_request_id=str(approval_request_id),
                    )
                # Rejected / cancelled / expired -> deny
                return PolicyResult(
                    decision=PolicyDecision.DENY,
                    reason=f"Approval not granted: status={status.value if status else status}",
                    approval_request_id=str(approval_request_id),
                )
            except Exception:
                # Fail-open in Phase 3 for compatibility.
                return PolicyResult(decision=PolicyDecision.ALLOW)

        try:
            from core.harness.infrastructure.approval import ApprovalContext, RequestStatus

            ctx = ApprovalContext(
                session_id=str((tool_args or {}).get("_session_id", "default")),
                user_id=user_id,
                operation=f"tool:{tool_name}",
                operation_context={"tool": tool_name, "args": tool_args or {}},
                metadata={
                    "tool_name": tool_name,
                    "risk_level": (tool_args or {}).get("_risk_level"),
                    "risk_weight": (tool_args or {}).get("_risk_weight"),
                },
            )
            req = approval_mgr.check_and_request(ctx)
            # Ensure request metadata includes risk fields (ApprovalManager persists metadata).
            try:
                if hasattr(req, "metadata") and isinstance(ctx.metadata, dict):
                    req.metadata = dict(getattr(req, "metadata", {}) or {})
                    req.metadata.setdefault("risk_level", ctx.metadata.get("risk_level"))
                    req.metadata.setdefault("risk_weight", ctx.metadata.get("risk_weight"))
                    req.metadata.setdefault("tool_name", ctx.metadata.get("tool_name"))
            except Exception:
                pass
            status = getattr(req, "status", None)
            if status in (RequestStatus.PENDING, RequestStatus.REJECTED):
                return PolicyResult(
                    decision=PolicyDecision.APPROVAL_REQUIRED,
                    reason=f"Tool '{tool_name}' requires approval",
                    approval_request_id=getattr(req, "request_id", None) or getattr(req, "id", None),
                )
        except Exception:
            # Fail-open in Phase 3 for compatibility.
            return PolicyResult(decision=PolicyDecision.ALLOW)

        return PolicyResult(decision=PolicyDecision.ALLOW)
