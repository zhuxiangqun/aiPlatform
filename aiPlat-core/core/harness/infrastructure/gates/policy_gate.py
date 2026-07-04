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
from typing import Any, Dict, List, Optional
import os
import hashlib
import fnmatch
import logging
import os

logger = logging.getLogger(__name__)

from core.apps.tools.permission import Permission  # noqa: allowed — data type (enum)
from core.harness.kernel.runtime import get_kernel_runtime
from core.policy.engine import evaluate_tool_policy_snapshot, PolicyDecision as EngineDecision
# DI: resolve_skill_permission via SkillPermissionResolver


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


# ── Architecture boundary enforcement (§5.1, §5.29, §5.30) ──────

# Layer definition: which directories belong to which layer
_ARCH_LAYERS = {
    "core": ["aiPlat-core/core/", "aiPlat-core/"],
    "platform": ["aiPlat-platform/"],
    "infra": ["aiPlat-infra/"],
    "app": ["aiPlat-app/"],
}

# Which layers are PROTECTED — writes from other layers are denied
_LAYER_PROTECTION = {
    "core": ["platform", "app"],       # platform/app must not write to core/
    "infra": ["core", "platform", "app"],  # no layer writes to infra except infra
    "platform": [],                      # platform can be written by platform (own layer)
}


def _check_arch_boundary(filepath: str, tool_name: str) -> Optional[str]:
    u"""Check if a file write crosses protected layer boundaries.

    Returns: violation reason string if denied, None if allowed.
    """
    path = str(filepath)
    # Determine which layer the file belongs to
    target_layer = None
    for layer, prefixes in _ARCH_LAYERS.items():
        for prefix in prefixes:
            if prefix in path:
                target_layer = layer
                break
        if target_layer:
            break

    if not target_layer:
        return None  # outside project scope — allow

    # infra is fully protected — no external writes
    if target_layer == "infra":
        return f"architecture_violation: writing to infra/ layer is protected. Use infra-specific APIs."

    # core is protected from platform/app
    if target_layer == "core":
        return f"architecture_violation: writing to core/ from non-core layer is forbidden. Use CoreFacade."

    return None  # allowed


@__import__("functools").lru_cache(maxsize=1)
def _get_protected_paths() -> set:
    """Load protected paths (cached in memory, refreshed on restart)."""
    protected = {"/**/auth/**", "/**/crypto/**", "/**/migration/**",
                 "/**/billing/**", "/**/payment/**", "/**/security/**",
                 "/**/secrets/**", "/**/.env*", "/**/credentials/**"}
    try:
        import yaml
        rules_file = __import__("pathlib").Path(__file__).resolve().parent.parent.parent.parent.parent.parent.parent
        rules_file = rules_file / "aiPlat-core" / "core" / "management" / "arch_guard_rules.yaml"
        if rules_file.exists():
            with open(rules_file) as f:
                data = yaml.safe_load(f)
            for rule in data.get("rules", []):
                af = rule.get("auto_fix", {})
                if af.get("enabled") and af.get("safety_level") == "high":
                    for p in rule.get("check", {}).get("paths", []):
                        protected.add(p)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return protected


def _check_protected_paths(filepath: str) -> str:
    """Check if filepath matches any protected path pattern. Returns reason or ''."""
    import fnmatch
    path = str(filepath)
    for pattern in _get_protected_paths():
        if fnmatch.fnmatch(path, pattern) or pattern.strip("*") in path:
            return f"'{path}' matches protected pattern '{pattern}'"
    return ""


class PolicyGate:
    def __init__(self) -> None:
        # Dev escape hatch: disable approvals entirely.
        # This keeps RBAC checks, but bypasses approval_required gating.
        self._disable_approvals = os.getenv("AIPLAT_APPROVALS_DISABLED", "false").lower() in (
            "1",
            "true",
            "yes",
            "y",
        )
        # Default: do NOT enforce approval in syscall yet to avoid double approval.
        # Phase 4+: we will move approval fully into sys_tool and remove loop-level checks.
        self._enforce_approval = os.getenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false").lower() in (  # noqa: planned-phase4
            "1",
            "true",
            "yes",
            "y",
        )

    @staticmethod
    def check_route_access(path: str, role: str) -> bool:
        """Route-level access control — check if role can access this path.

        Matches path against ROUTE_PERMISSIONS using prefix matching.
        Each route entry defines which roles are allowed.
        """
        from core.schemas_policy import ROUTE_PERMISSIONS
        for route_prefix, allowed_roles in ROUTE_PERMISSIONS.items():
            if path.startswith(route_prefix):
                return role in allowed_roles
        # No matching route → allow (backward compatibility)
        return True

    @staticmethod
    def _match_tool_rule(rule: Dict[str, Any], tool_name: str, tool_args: Optional[Dict[str, Any]]) -> bool:
        """P1-1: Match rule against tool name + optional params (fnmatch + re support)."""
        import fnmatch
        rule_tool = rule.get("tool", "")
        if not rule_tool:
            return False
        # Tool name match: exact or fnmatch
        if not (rule_tool == tool_name or fnmatch.fnmatch(tool_name, rule_tool)):
            return False
        # Param-level match (optional)
        rule_params = rule.get("params") or {}
        if not rule_params:
            return True
        args = tool_args or {}
        for k, v in rule_params.items():
            actual = str(args.get(k, ""))
            if not fnmatch.fnmatch(actual, str(v)):
                return False
        return True

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
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
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
        """Single-point permission enforcement for tool execution (§11)."""
        if self._disable_approvals:
            return PolicyResult(decision=PolicyDecision.ALLOW)

        # P2-19: ApprovalGate — dangerous command detection before permission check
        try:
            from core.harness.infrastructure.gates.approval_gate import get_approval_gate, ApprovalVerdict
            approval_gate = get_approval_gate()
            approval_result = approval_gate.check(
                tool_name=tool_name,
                tool_args=tool_args or {},
                user_id=user_id,
                session_id=(tool_args or {}).get("_session_id", "") if isinstance(tool_args, dict) else "",
            )
            if approval_result.verdict == ApprovalVerdict.DENY:
                return PolicyResult(
                    decision=PolicyDecision.DENY,
                    reason=f"approval_gate:deny — {approval_result.message}",
                )
            if approval_result.verdict == ApprovalVerdict.ASK:
                return PolicyResult(
                    decision=PolicyDecision.APPROVAL_REQUIRED,
                    reason=f"approval_gate:ask — {approval_result.message}",
                )
        except ImportError:
            logging.debug("ApprovalGate module not available — skipping dangerous command check")
        except Exception as e:
            logging.warning("ApprovalGate check failed: %s — gate remains active", e)

        # P1-1: Three-layer rule priority (deny > ask > allow) with param-level matching
        from core.harness.integration import get_permission_manager
        perm_mgr = get_permission_manager()
        rules = getattr(perm_mgr, "_permission_rules", None) or []
        # Sort: deny first, then ask, then allow
        for rule in sorted(rules, key=lambda r: {"deny": 0, "ask": 1, "allow": 2}.get(r.get("action", ""), 99)):
            if not self._match_tool_rule(rule, tool_name, tool_args):
                continue
            if rule["action"] == "deny":
                return PolicyResult(decision=PolicyDecision.DENY, reason=rule.get("reason", "denied by policy"))
            if rule["action"] == "ask":
                return PolicyResult(decision=PolicyDecision.ASK, reason=rule.get("reason", "requires approval"))

        if not perm_mgr.check_permission(user_id, tool_name, Permission.EXECUTE):
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason=f"User '{user_id}' lacks EXECUTE permission for tool '{tool_name}'",
            )

        # Architecture boundary check: deny cross-layer file writes
        if tool_name and any(kw in str(tool_name).lower() for kw in ("file_write", "file_edit", "sys_file_write", "sys_file_edit")):
            path = (tool_args or {}).get("path") or (tool_args or {}).get("file") or (tool_args or {}).get("filepath") or ""
            if path and isinstance(path, str):
                arch_violation = _check_arch_boundary(path, tool_name)
                if arch_violation:
                    return PolicyResult(
                        decision=PolicyDecision.DENY,
                        reason=arch_violation,
                    )
                # Protected paths check: deny writes to security-critical directories
                protected_violation = _check_protected_paths(path)
                if protected_violation:
                    return PolicyResult(
                        decision=PolicyDecision.DENY,
                        reason=f"protected_path: {protected_violation}",
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
                from core.api.core_facade import resolve_skill_permission
                decision = resolve_skill_permission(sname)
                if decision == "deny":
                    return PolicyResult(
                        decision=PolicyDecision.DENY,
                        reason=f"skill_load denied for '{sname}' by AIPLAT_SKILL_PERMISSION_RULES",
                        tenant_id=str(tenant_id) if tenant_id else None,
                    )
                if decision == "ask":
                    force_approval = True
        except Exception as e:
            logging.debug(str(e), exc_info=True)
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
        except Exception as e:
            # Fail-open for compatibility.
            logging.debug(str(e), exc_info=True)

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
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
            req = approval_mgr.check_and_request(ctx)
            # Ensure request metadata includes risk fields (ApprovalManager persists metadata).
            try:
                if hasattr(req, "metadata") and isinstance(ctx.metadata, dict):
                    req.metadata = dict(getattr(req, "metadata", {}) or {})
                    req.metadata.setdefault("risk_level", ctx.metadata.get("risk_level"))
                    req.metadata.setdefault("risk_weight", ctx.metadata.get("risk_weight"))
                    req.metadata.setdefault("tool_name", ctx.metadata.get("tool_name"))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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
        if self._disable_approvals:
            return PolicyResult(decision=PolicyDecision.ALLOW)

        # Permission check (consistent with tools). For unit/internals with no request context, fail-open.
        try:
            from core.harness.kernel.execution_context import get_active_request_context

            if get_active_request_context() is not None:
                from core.harness.integration import get_permission_manager
                perm_mgr = get_permission_manager()
                if not perm_mgr.check_permission(user_id, str(skill_name or ""), Permission.EXECUTE):
                    return PolicyResult(
                        decision=PolicyDecision.DENY,
                        reason=f"User '{user_id}' lacks EXECUTE permission for skill '{skill_name}'",
                    )
        except Exception as e:
            # Fail-open for compatibility (Phase 3).
            logging.debug(str(e), exc_info=True)
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
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
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

    async def check_agent(self, *, user_id: str, agent_id: str, agent_args: Optional[Dict[str, Any]] = None) -> PolicyResult:
        """Governance for agent execution. Enforces RBAC permission + optional approval sampling."""
        args = agent_args if isinstance(agent_args, dict) else {}
        if self._disable_approvals:
            return PolicyResult(decision=PolicyDecision.ALLOW)
        try:
            from core.harness.kernel.execution_context import get_active_request_context
            if get_active_request_context() is not None:
                from core.harness.integration import get_permission_manager
                perm_mgr = get_permission_manager()
                if not perm_mgr.check_permission(user_id, str(agent_id or ""), Permission.EXECUTE):
                    return PolicyResult(decision=PolicyDecision.DENY, reason=f"User '{user_id}' lacks EXECUTE permission for agent '{agent_id}'")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        force_approval = bool(args.get("_approval_required"))
        try:
            force_approval, _ = await self._maybe_waive_approval(operation=f"agent:{agent_id}", force_approval=force_approval,
                tenant_id=str(args.get("_tenant_id")) if args.get("_tenant_id") else None,
                args=args if isinstance(args, dict) else None)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        if not force_approval:
            return PolicyResult(decision=PolicyDecision.ALLOW)
        # Approval flow (same as check_skill)
        runtime = get_kernel_runtime()
        approval_mgr = getattr(runtime, "approval_manager", None) if runtime else None
        if not approval_mgr:
            return PolicyResult(decision=PolicyDecision.ALLOW) if not force_approval else PolicyResult(decision=PolicyDecision.APPROVAL_REQUIRED, reason=f"Agent '{agent_id}' requires approval")
        try:
            from core.harness.infrastructure.approval.types import ApprovalContext
            req = approval_mgr.check_and_request(ApprovalContext(
                operation=f"agent:{agent_id}", user_id=user_id,
                tenant_id=str(args.get("_tenant_id")) if args.get("_tenant_id") else None,
                metadata={"agent_id": str(agent_id)}))
            status = getattr(req, "status", None)
            from core.harness.infrastructure.approval.types import RequestStatus
            if status in (RequestStatus.PENDING, RequestStatus.REJECTED):
                return PolicyResult(decision=PolicyDecision.APPROVAL_REQUIRED, reason=f"Agent '{agent_id}' requires approval",
                    approval_request_id=getattr(req, "request_id", None) or getattr(req, "id", None))
        except Exception:
            return PolicyResult(decision=PolicyDecision.ALLOW)
        return PolicyResult(decision=PolicyDecision.ALLOW)

    async def check_workflow(self, *, user_id: str, workflow_id: str, workflow_args: Optional[Dict[str, Any]] = None) -> PolicyResult:
        """Governance for workflow execution. Enforces RBAC permission + optional approval."""
        args = workflow_args if isinstance(workflow_args, dict) else {}
        if self._disable_approvals:
            return PolicyResult(decision=PolicyDecision.ALLOW)
        try:
            from core.harness.kernel.execution_context import get_active_request_context
            if get_active_request_context() is not None:
                from core.harness.integration import get_permission_manager
                perm_mgr = get_permission_manager()
                if not perm_mgr.check_permission(user_id, str(workflow_id or ""), Permission.EXECUTE):
                    return PolicyResult(decision=PolicyDecision.DENY, reason=f"User '{user_id}' lacks EXECUTE permission for workflow '{workflow_id}'")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        force_approval = bool(args.get("_approval_required"))
        try:
            force_approval, _ = await self._maybe_waive_approval(operation=f"workflow:{workflow_id}", force_approval=force_approval,
                tenant_id=str(args.get("_tenant_id")) if args.get("_tenant_id") else None,
                args=args if isinstance(args, dict) else None)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        if not force_approval:
            return PolicyResult(decision=PolicyDecision.ALLOW)
        return PolicyResult(decision=PolicyDecision.APPROVAL_REQUIRED, reason=f"Workflow '{workflow_id}' requires approval")


async def check_stage_ontology_guard(
    stage: Any,
    state: Dict[str, Any],
    collection_id: str = "default",
) -> Optional[str]:
    u"""Check ontology constraints before pipeline stage execution.

    Returns violation reason string if blocked, None if allowed.
    Currently enforces:
      - A1: ConceptPage must have at least one valid KB document source.
      - Unresolved contradictions in entities the stage depends on.

    Args:
        stage: PipelineStageConfig instance.
        state: pipeline state dict.
        collection_id: wiki collection scope.

    Returns:
        Violation string or None.
    """
    AI = "http://aiplat.local/knowledge#"
    ontology_class = getattr(stage, 'ontology_class', '') or ''
    ontology_relations = getattr(stage, 'ontology_relations', None) or []

    if not ontology_class:
        return None  # stage not producing ontology entities — skip

    # A1 guard: ConceptPage must reference existing KB documents
    if ontology_class == "ConceptPage":
        for rel in ontology_relations:
            if not isinstance(rel, dict):
                continue
            target_doc = rel.get("target_kb_doc", "")
            if not target_doc:
                continue

            # Check if KBDocument exists in onto A-Box
            try:
                from core.harness.knowledge.knowledge_ontology import get_ontology
                onto = get_ontology()
                kb_uri = f"{AI}{target_doc}"
                alias_uri = f"{AI}kb:{target_doc.lstrip('kb:')}"

                exists = any(
                    t.predicate == "rdf:type"
                    and f"{AI}KBDocument" in t.object
                    and t.subject in (kb_uri, alias_uri)
                    for t in onto.triples
                )

                if not exists:
                    return (
                        f"Ontology A1 violation: KB document '{target_doc}' not registered. "
                        f"Stage '{getattr(stage, 'id', '?')}' would produce a source-less ConceptPage."
                    )
            except Exception as e:
                return f"Ontology guard: failed to check KB document existence — {e}"

    # Contradiction guard: warn if dependencies reference contradicted entities
    input_artifacts = getattr(stage, 'input_artifacts', None) or []
    if input_artifacts:
        try:
            from core.harness.knowledge.knowledge_ontology import get_ontology
            AI = "http://aiplat.local/knowledge#"
            onto = get_ontology()
            contradicted = {
                t.subject.replace(AI, "")
                for t in onto.triples
                if t.predicate == f"{AI}lifecycleState"
                and t.object.strip('"') == "contradicted"
            }

            for art_key in input_artifacts:
                art = state.get(art_key)
                if isinstance(art, dict):
                    for ref_title in art.values():
                        if isinstance(ref_title, str) and ref_title in contradicted:
                            # Warning only — don't block execution
                            import logging
                            logging.getLogger("policy_gate").warning(
                                "Ontology: stage %s depends on contradicted entity '%s'",
                                getattr(stage, 'id', '?'), ref_title,
                            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    return None


async def check_kb_access(
    entity_uri: str,
    action: str,
    actor_role: str = "",
    actor_scopes: Optional[List[str]] = None,
    tenant_id: str = "default",
    collection_id: str = "default",
) -> PolicyResult:
    u"""Three-layer fused permission computation for knowledge base access.

    Layer 1 — RBAC scope coarse filter.
    Layer 2 — Markings lineage check (propagated via ontology relations).
    Layer 3 — Per-object permission fine check.

    Any layer DENY → overall DENY. Reason MUST state which layer blocked.
    """
    actor_scopes = actor_scopes or []
    actor_scopes_set = set(actor_scopes)

    # Layer 1: RBAC scope check
    action_scope_map = {
        "read": ["kb:read", "agent:read", "skill:read"],
        "read_body": ["kb:read", "agent:read"],
        "cite": ["kb:read", "agent:execute"],
        "update": ["kb:write"],
        "state_change": ["kb:write"],
        "delete": ["kb:write"],
        "admin": ["admin"],
    }
    required_scopes = set(action_scope_map.get(action, ["kb:read"]))
    if "admin" not in actor_scopes_set:
        if required_scopes and not (required_scopes & actor_scopes_set):
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason=f"Layer1-RBAC: lacks scopes {sorted(required_scopes)} (has {sorted(actor_scopes_set)})",
            )

    # Layer 2: Markings check
    try:
        from core.harness.knowledge.knowledge_markings import (
            load_markings_config, resolve_effective_markings, MarkingLevel,
        )
        from core.harness.knowledge.knowledge_ontology import get_ontology

        marking_config = load_markings_config(collection_id)
        onto = get_ontology()
        effective, _traces = resolve_effective_markings(
            entity_uri, marking_config, onto.triples, max_depth=5,
        )
        for m in effective:
            if m.level >= MarkingLevel.INTERNAL:
                required_scope = m.scope or f"kb:read:{m.label.lower()}"
                if "admin" not in actor_scopes_set and required_scope not in actor_scopes_set:
                    return PolicyResult(
                        decision=PolicyDecision.DENY,
                        reason=(
                            f"Layer2-Marking: entity requires scope '{required_scope}' "
                            f"due to '{m.label}' (level={m.level.name}"
                            f", from {m.propagated_from or 'direct'})"
                        ),
                    )
    except Exception as e:
        logger.warning("Marking check failed for %s: %s", entity_uri, str(e)[:200])

    # Layer 3: Per-object permission (optional — only enforced when explicitly defined)
    try:
        from core.policy.object_permission import check_object_permission
        from core.policy.object_permission import _load as _load_perms
        all_perms = _load_perms(collection_id)
        entity_has_rules = any(p.entity_uri == entity_uri for p in all_perms)
        if entity_has_rules and not check_object_permission(
            entity_uri, actor_role, action,
            tenant_id=tenant_id, collection_id=collection_id,
        ):
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason=(
                    f"Layer3-ObjectPerm: no permission for "
                    f"role='{actor_role}' action='{action}' on '{entity_uri}'"
                ),
            )
    except Exception as e:
        logger.warning("Object permission check failed for %s: %s", entity_uri, str(e)[:200])

    return PolicyResult(decision=PolicyDecision.ALLOW)

