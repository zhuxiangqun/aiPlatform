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
import hashlib
import fnmatch

from core.apps.tools.permission import get_permission_manager, Permission
from core.harness.kernel.runtime import get_kernel_runtime
from core.policy.engine import evaluate_tool_policy_snapshot, PolicyDecision as EngineDecision
from core.apps.tools.skill_tools import resolve_skill_permission


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


@dataclass
class PolicyResult:
    decision: PolicyDecision
    reason: Optional[str] = None
    approval_request_id: Optional[str] = None
    tenant_id: Optional[str] = None
    policy_version: Optional[int] = None


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

    def _load_approval_review_policy(self, *, tenant_policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        P6-3: approval review strategy (sampling/exception review).

        Tenant policy overrides env defaults.

        Schema (tenant policy):
          policy.approval_review = {
            "mode": "always|sample|risk_sample|never",
            "sample_rate": 0.1,
            "high_risk_always": true,
            "force_list": "tool:repo,skill:danger-*",
            "bypass_list": "tool:skill_find",
            "seed": "optional"
          }
        """
        mode = str(os.getenv("AIPLAT_APPROVAL_REVIEW_MODE", "always") or "always").strip().lower()
        try:
            sample_rate = float(os.getenv("AIPLAT_APPROVAL_SAMPLE_RATE", "0") or "0")
        except Exception:
            sample_rate = 0.0
        high_risk_always = os.getenv("AIPLAT_APPROVAL_HIGH_RISK_ALWAYS", "true").lower() in {"1", "true", "yes", "y"}
        force_list = str(os.getenv("AIPLAT_APPROVAL_FORCE_LIST", "") or "").strip()
        bypass_list = str(os.getenv("AIPLAT_APPROVAL_BYPASS_LIST", "") or "").strip()
        seed = str(os.getenv("AIPLAT_APPROVAL_SAMPLE_SEED", "") or "").strip()

        t = tenant_policy.get("approval_review") if isinstance(tenant_policy, dict) else None
        if isinstance(t, dict):
            if isinstance(t.get("mode"), str) and str(t.get("mode")).strip():
                mode = str(t.get("mode")).strip().lower()
            if t.get("sample_rate") is not None:
                try:
                    sample_rate = float(t.get("sample_rate"))
                except Exception:
                    pass
            if isinstance(t.get("high_risk_always"), bool):
                high_risk_always = bool(t.get("high_risk_always"))
            if isinstance(t.get("force_list"), str):
                force_list = str(t.get("force_list")).strip()
            if isinstance(t.get("bypass_list"), str):
                bypass_list = str(t.get("bypass_list")).strip()
            if isinstance(t.get("seed"), str):
                seed = str(t.get("seed")).strip()

        # clamp
        if sample_rate < 0:
            sample_rate = 0.0
        if sample_rate > 1:
            sample_rate = 1.0
        if mode not in {"always", "sample", "risk_sample", "never"}:
            mode = "always"
        return {
            "mode": mode,
            "sample_rate": float(sample_rate),
            "high_risk_always": bool(high_risk_always),
            "force_list": force_list,
            "bypass_list": bypass_list,
            "seed": seed,
        }

    def _match_list(self, operation: str, raw: str) -> bool:
        pats = [p.strip() for p in str(raw or "").split(",") if p.strip()]
        if not pats:
            return False
        for pat in pats:
            try:
                if fnmatch.fnmatch(operation, pat):
                    return True
            except Exception:
                continue
        return False

    def _deterministic_sample(self, *, key: str, rate: float) -> bool:
        """
        Deterministic sampling in [0,1): use sha256(key) mod 10000.
        """
        try:
            h = hashlib.sha256(str(key).encode("utf-8")).hexdigest()
            v = int(h[:8], 16) % 10000
            return v < int(rate * 10000)
        except Exception:
            return False

    async def _maybe_waive_approval(
        self,
        *,
        operation: str,
        force_approval: bool,
        tenant_id: Optional[str],
        policy_version: Optional[int],
        args: Optional[Dict[str, Any]],
    ) -> tuple[bool, Optional[str]]:
        """
        Returns: (new_force_approval, waive_reason_if_any)
        """
        if not force_approval:
            return False, None
        if not isinstance(args, dict):
            return True, None
        # if resuming with explicit approval id, never waive
        if args.get("_approval_request_id"):
            return True, None
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        tenant_pol = None
        if tenant_id and store and hasattr(store, "get_tenant_policy"):
            try:
                rec = await store.get_tenant_policy(tenant_id=str(tenant_id))
                tenant_pol = rec.get("policy") if isinstance(rec, dict) and isinstance(rec.get("policy"), dict) else None
                if policy_version is None and isinstance(rec, dict) and rec.get("version") is not None:
                    try:
                        policy_version = int(rec.get("version"))
                    except Exception:
                        policy_version = policy_version
            except Exception:
                tenant_pol = None
        pol = self._load_approval_review_policy(tenant_policy=tenant_pol if isinstance(tenant_pol, dict) else None)
        mode = pol.get("mode")
        # explicit allow/deny lists
        if self._match_list(operation, pol.get("bypass_list")):
            return False, f"bypass_list:{operation}"
        if self._match_list(operation, pol.get("force_list")):
            return True, f"force_list:{operation}"
        if mode == "always":
            return True, None
        if mode == "never":
            return False, f"mode_never:{operation}"

        risk_level = str(args.get("_risk_level") or "").strip().lower()
        if pol.get("high_risk_always") and risk_level in {"high", "critical"}:
            return True, "high_risk_always"

        rate = float(pol.get("sample_rate") or 0.0)
        if rate <= 0:
            return False, "sample_rate_0"
        if rate >= 1:
            return True, "sample_rate_1"

        seed = str(pol.get("seed") or "").strip() or str(tenant_id or "")
        run_id = str(args.get("_run_id") or args.get("_session_id") or "")
        key = f"{seed}:{tenant_id}:{operation}:{run_id}"
        hit = self._deterministic_sample(key=key, rate=rate)
        if mode == "sample":
            return (True, f"sample_hit:{rate}") if hit else (False, f"sample_miss:{rate}")
        # risk_sample: treat non-high as sample; high handled above
        return (True, f"risk_sample_hit:{rate}") if hit else (False, f"risk_sample_miss:{rate}")

    async def check_tool(self, *, user_id: str, tool_name: str, tool_args: Optional[Dict[str, Any]] = None) -> PolicyResult:
        perm_mgr = get_permission_manager()
        if not perm_mgr.check_permission(user_id, tool_name, Permission.EXECUTE):
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason=f"User '{user_id}' lacks EXECUTE permission for tool '{tool_name}'",
            )

        # PR-07: unify policy decisions via policy_engine（同步版）
        tenant_id = (tool_args or {}).get("_tenant_id") if isinstance(tool_args, dict) else None
        policy_version: Optional[int] = None
        force_approval = bool((tool_args or {}).get("_approval_required")) if isinstance(tool_args, dict) else False

        # Skills (OpenCode style): per-skill allow/deny/ask for skill_load.
        # This is evaluated BEFORE reading tenant policy snapshots so that local rule config
        # can immediately hide/deny risky skills and request approval when needed.
        try:
            if str(tool_name).strip().lower() == "skill_load" and isinstance(tool_args, dict):
                sname = str(tool_args.get("name") or tool_args.get("skill") or "").strip()
                decision = resolve_skill_permission(sname)
                if decision == "deny":
                    return PolicyResult(
                        decision=PolicyDecision.DENY,
                        reason=f"skill_load denied for '{sname}' by AIPLAT_SKILL_PERMISSION_RULES",
                        tenant_id=str(tenant_id) if tenant_id else None,
                    )
                if decision == "ask":
                    force_approval = True
        except Exception:
            pass
        try:
            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            if os.getenv("AIPLAT_POLICY_ENGINE", "1").lower() not in ("0", "false", "no", "n"):
                # Read policy snapshot (store) and evaluate locally.
                pol = None
                if tenant_id and store:
                    try:
                        if hasattr(store, "get_tenant_policy"):
                            rec = await store.get_tenant_policy(tenant_id=str(tenant_id))
                            if isinstance(rec, dict):
                                pol = rec.get("policy") if isinstance(rec.get("policy"), dict) else None
                                try:
                                    policy_version = int(rec.get("version")) if rec.get("version") is not None else None
                                except Exception:
                                    policy_version = None
                    except Exception:
                        pol = None
                ev = evaluate_tool_policy_snapshot(
                    policy=pol if isinstance(pol, dict) else None,
                    policy_version=policy_version,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    actor_id=user_id,
                    actor_role=(tool_args or {}).get("_actor_role") if isinstance(tool_args, dict) else None,
                    tool_name=str(tool_name),
                    tool_args=tool_args if isinstance(tool_args, dict) else None,
                )
                if ev.decision == EngineDecision.DENY:
                    return PolicyResult(
                        decision=PolicyDecision.DENY,
                        reason=ev.reason,
                        tenant_id=ev.tenant_id,
                        policy_version=policy_version,
                    )
                if ev.decision == EngineDecision.APPROVAL_REQUIRED:
                    force_approval = True
        except Exception:
            # Fail-open for compatibility.
            pass

        # P6-3: approval sampling/exception review (best-effort)
        waive_reason = None
        try:
            force_approval, waive_reason = await self._maybe_waive_approval(
                operation=f"tool:{tool_name}",
                force_approval=force_approval,
                tenant_id=str(tenant_id) if tenant_id else None,
                policy_version=policy_version,
                args=tool_args if isinstance(tool_args, dict) else None,
            )
        except Exception:
            waive_reason = None

        # If no approval required, allow immediately (even when enforce flag is on).
        if not force_approval:
            # best-effort observability
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                rid = (tool_args or {}).get("_run_id") if isinstance(tool_args, dict) else None
                if store and rid and waive_reason:
                    await store.append_run_event(
                        run_id=str(rid),
                        event_type="approval_waived",
                        trace_id=None,
                        tenant_id=str(tenant_id) if tenant_id else None,
                        payload={"operation": f"tool:{tool_name}", "reason": waive_reason, "policy_version": policy_version},
                    )
            except Exception:
                pass
            return PolicyResult(decision=PolicyDecision.ALLOW)

        runtime = get_kernel_runtime()
        approval_mgr = getattr(runtime, "approval_manager", None) if runtime else None
        if not approval_mgr:
            # If approval is being enforced (explicitly or via tenant policy), fail-closed.
            if force_approval:
                return PolicyResult(
                    decision=PolicyDecision.APPROVAL_REQUIRED,
                    reason=f"Tool '{tool_name}' requires approval (approval manager not initialized)",
                    tenant_id=str(tenant_id) if tenant_id else None,
                    policy_version=policy_version,
                )
            return PolicyResult(decision=PolicyDecision.ALLOW)

        # If caller provides an approval_request_id, honor it (resume semantics).
        approval_request_id = (tool_args or {}).get("_approval_request_id") if isinstance(tool_args, dict) else None
        if approval_request_id:
            try:
                req = None
                if hasattr(approval_mgr, "get_request_async"):
                    req = await approval_mgr.get_request_async(str(approval_request_id))
                else:
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
            from core.harness.infrastructure.approval.types import ApprovalRule, RuleType

            ctx = ApprovalContext(
                session_id=str((tool_args or {}).get("_session_id", "default")),
                user_id=user_id,
                operation=f"tool:{tool_name}",
                operation_context={"tool": tool_name, "args": tool_args or {}},
                metadata={
                    "tool_name": tool_name,
                    "risk_level": (tool_args or {}).get("_risk_level"),
                    "risk_weight": (tool_args or {}).get("_risk_weight"),
                    # PR-08: identity/run linkage for approval hub & replay
                    "tenant_id": (tool_args or {}).get("_tenant_id"),
                    "actor_id": user_id,
                    "actor_role": (tool_args or {}).get("_actor_role"),
                    "session_id": str((tool_args or {}).get("_session_id", "default")),
                    "run_id": (tool_args or {}).get("_run_id"),
                    # Plan fields (MVP)
                    "system_run_plan": {
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args or {},
                    },
                },
            )
            # PR-08: when force_approval is true, ensure a matching rule exists (otherwise manager auto-approves).
            if force_approval:
                try:
                    rid = f"tool_force_approval:{tool_name}"
                    approval_mgr.register_rule(
                        ApprovalRule(
                            rule_id=rid,
                            rule_type=RuleType.SENSITIVE_OPERATION,
                            name=f"工具调用审批：{tool_name}",
                            description=f"tool:{tool_name} requires approval",
                            priority=1,
                            metadata={"sensitive_operations": [ctx.operation]},
                        )
                    )
                except Exception:
                    pass
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

    async def check_skill(self, *, user_id: str, skill_name: str, skill_args: Optional[Dict[str, Any]] = None) -> PolicyResult:
        """
        Governance for executable skills.

        Design:
        - Reuse the same approval manager + policy engine machinery as tools
        - Default posture is deny/ask depending on env rules (handled in syscall wrapper)
        - Skill approval request is recorded as operation: "skill:<name>"
        """
        args = skill_args if isinstance(skill_args, dict) else {}

        # Permission check (consistent with tools). For unit/internals with no request context, fail-open.
        try:
            from core.harness.kernel.execution_context import get_active_request_context

            if get_active_request_context() is not None:
                perm_mgr = get_permission_manager()
                if not perm_mgr.check_permission(user_id, str(skill_name or ""), Permission.EXECUTE):
                    return PolicyResult(
                        decision=PolicyDecision.DENY,
                        reason=f"User '{user_id}' lacks EXECUTE permission for skill '{skill_name}'",
                    )
        except Exception:
            # Fail-open for compatibility (Phase 3).
            pass
        tenant_id = args.get("_tenant_id")
        policy_version: Optional[int] = None
        force_approval = bool(args.get("_approval_required"))

        # P6-3: approval sampling/exception review (best-effort)
        waive_reason = None
        try:
            force_approval, waive_reason = await self._maybe_waive_approval(
                operation=f"skill:{skill_name}",
                force_approval=force_approval,
                tenant_id=str(tenant_id) if tenant_id else None,
                policy_version=policy_version,
                args=args if isinstance(args, dict) else None,
            )
        except Exception:
            waive_reason = None

        if not force_approval:
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                rid = args.get("_run_id") if isinstance(args, dict) else None
                if store and rid and waive_reason:
                    await store.append_run_event(
                        run_id=str(rid),
                        event_type="approval_waived",
                        trace_id=None,
                        tenant_id=str(tenant_id) if tenant_id else None,
                        payload={"operation": f"skill:{skill_name}", "reason": waive_reason, "policy_version": policy_version},
                    )
            except Exception:
                pass
            return PolicyResult(decision=PolicyDecision.ALLOW)

        runtime = get_kernel_runtime()
        approval_mgr = getattr(runtime, "approval_manager", None) if runtime else None
        if not approval_mgr:
            if force_approval:
                return PolicyResult(
                    decision=PolicyDecision.APPROVAL_REQUIRED,
                    reason=f"Skill '{skill_name}' requires approval (approval manager not initialized)",
                    tenant_id=str(tenant_id) if tenant_id else None,
                    policy_version=policy_version,
                )
            return PolicyResult(decision=PolicyDecision.ALLOW)

        approval_request_id = args.get("_approval_request_id")
        if approval_request_id:
            try:
                req = None
                if hasattr(approval_mgr, "get_request_async"):
                    req = await approval_mgr.get_request_async(str(approval_request_id))
                else:
                    req = approval_mgr.get_request(str(approval_request_id))
                if not req:
                    return PolicyResult(
                        decision=PolicyDecision.APPROVAL_REQUIRED,
                        reason=f"Approval request not found: {approval_request_id}",
                        approval_request_id=str(approval_request_id),
                    )
                status = getattr(req, "status", None)
                from core.harness.infrastructure.approval.types import RequestStatus

                if status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
                    return PolicyResult(decision=PolicyDecision.ALLOW)
                if status == RequestStatus.PENDING:
                    return PolicyResult(
                        decision=PolicyDecision.APPROVAL_REQUIRED,
                        reason=f"Skill '{skill_name}' requires approval",
                        approval_request_id=str(approval_request_id),
                    )
                return PolicyResult(
                    decision=PolicyDecision.DENY,
                    reason=f"Approval not granted: status={status.value if status else status}",
                    approval_request_id=str(approval_request_id),
                )
            except Exception:
                return PolicyResult(decision=PolicyDecision.ALLOW)

        try:
            from core.harness.infrastructure.approval import ApprovalContext, RequestStatus
            from core.harness.infrastructure.approval.types import ApprovalRule, RuleType

            ctx = ApprovalContext(
                session_id=str(args.get("_session_id", "default")),
                user_id=user_id,
                operation=f"skill:{skill_name}",
                operation_context={"skill": skill_name, "args": args},
                metadata={
                    "skill_name": skill_name,
                    "tenant_id": tenant_id,
                    "actor_id": user_id,
                    "actor_role": args.get("_actor_role"),
                    "session_id": str(args.get("_session_id", "default")),
                    "run_id": args.get("_run_id"),
                    "system_run_plan": {"type": "skill_call", "skill": skill_name, "args": args},
                },
            )
            if force_approval:
                try:
                    rid = f"skill_force_approval:{skill_name}"
                    approval_mgr.register_rule(
                        ApprovalRule(
                            rule_id=rid,
                            rule_type=RuleType.SENSITIVE_OPERATION,
                            name=f"技能调用审批：{skill_name}",
                            description=f"skill:{skill_name} requires approval",
                            priority=1,
                            metadata={"sensitive_operations": [ctx.operation]},
                        )
                    )
                except Exception:
                    pass
            req = approval_mgr.check_and_request(ctx)
            status = getattr(req, "status", None)
            if status in (RequestStatus.PENDING, RequestStatus.REJECTED):
                return PolicyResult(
                    decision=PolicyDecision.APPROVAL_REQUIRED,
                    reason=f"Skill '{skill_name}' requires approval",
                    approval_request_id=getattr(req, "request_id", None) or getattr(req, "id", None),
                )
        except Exception:
            return PolicyResult(decision=PolicyDecision.ALLOW)

        return PolicyResult(decision=PolicyDecision.ALLOW)
