"""
Policy Engine（统一策略引擎） - PR-07

目标：
- 将“deny/warn/approval_required”等散落决策收敛为统一 policy_engine
- 先覆盖工具调用与 MCP runtime 的生产环境安全策略
- tenant 维度策略存储：ExecutionStore.tenant_policies（已存在）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple
import os


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


@dataclass
class PolicyEvalResult:
    decision: PolicyDecision
    reason_code: str
    reason: str
    tenant_id: Optional[str] = None
    policy_version: Optional[int] = None
    matched_rule: Optional[str] = None
    metadata: Dict[str, Any] = None  # type: ignore[assignment]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "tenant_id": self.tenant_id,
            "policy_version": self.policy_version,
            "matched_rule": self.matched_rule,
            "metadata": self.metadata or {},
        }


def _get_tool_policy(policy: Any) -> Dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    tp = policy.get("tool_policy")
    return tp if isinstance(tp, dict) else {}


def evaluate_tool_policy_snapshot(
    *,
    policy: Optional[Dict[str, Any]],
    policy_version: Optional[int],
    tenant_id: Optional[str],
    actor_id: Optional[str],
    actor_role: Optional[str],
    tool_name: str,
    tool_args: Optional[Dict[str, Any]] = None,
) -> PolicyEvalResult:
    """在已获取 tenant policy snapshot 的情况下做纯计算（同步友好）。"""
    tid = str(tenant_id or "").strip() or None
    tp = _get_tool_policy(policy)

    deny_tools = tp.get("deny_tools") if isinstance(tp.get("deny_tools"), list) else []
    approval_tools = tp.get("approval_required_tools") if isinstance(tp.get("approval_required_tools"), list) else []
    allowed_tools = tp.get("allowed_tools") if isinstance(tp.get("allowed_tools"), list) else None

    if isinstance(allowed_tools, list) and allowed_tools:
        if "*" not in allowed_tools and str(tool_name) not in {str(x) for x in allowed_tools}:
            return PolicyEvalResult(
                decision=PolicyDecision.DENY,
                reason_code="TOOL_NOT_ALLOWED",
                reason=f"tool '{tool_name}' not in tenant allowlist",
                tenant_id=tid,
                policy_version=policy_version,
                matched_rule="tool_policy.allowed_tools",
                metadata={"actor_id": actor_id, "actor_role": actor_role},
            )

    if "*" in deny_tools or str(tool_name) in {str(x) for x in deny_tools}:
        return PolicyEvalResult(
            decision=PolicyDecision.DENY,
            reason_code="TENANT_POLICY_DENY",
            reason=f"Denied by tenant policy (tenant_id={tid}, version={policy_version})",
            tenant_id=tid,
            policy_version=policy_version,
            matched_rule="tool_policy.deny_tools",
            metadata={"actor_id": actor_id, "actor_role": actor_role},
        )

    force_approval = bool((tool_args or {}).get("_approval_required")) if isinstance(tool_args, dict) else False
    if "*" in approval_tools or str(tool_name) in {str(x) for x in approval_tools}:
        force_approval = True

    if force_approval:
        return PolicyEvalResult(
            decision=PolicyDecision.APPROVAL_REQUIRED,
            reason_code="TENANT_POLICY_APPROVAL_REQUIRED",
            reason=f"Approval required by tenant policy (tenant_id={tid}, version={policy_version})",
            tenant_id=tid,
            policy_version=policy_version,
            matched_rule="tool_policy.approval_required_tools",
            metadata={"actor_id": actor_id, "actor_role": actor_role},
        )

    return PolicyEvalResult(
        decision=PolicyDecision.ALLOW,
        reason_code="ALLOW",
        reason="allowed",
        tenant_id=tid,
        policy_version=policy_version,
        matched_rule=None,
        metadata={"actor_id": actor_id, "actor_role": actor_role},
    )


async def _load_tenant_policy_snapshot(*, store: Any, tenant_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """Return (policy_json, version)."""
    if not store or not tenant_id:
        return None, None
    try:
        item = await store.get_tenant_policy(tenant_id=str(tenant_id))
    except Exception:
        item = None
    if not isinstance(item, dict):
        return None, None
    pol = item.get("policy") if isinstance(item.get("policy"), dict) else None
    ver = item.get("version")
    try:
        ver_i = int(ver) if ver is not None else None
    except Exception:
        ver_i = None
    return pol, ver_i


async def evaluate_tool(
    *,
    store: Any,
    tenant_id: Optional[str],
    actor_id: Optional[str],
    actor_role: Optional[str],
    tool_name: str,
    tool_args: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> PolicyEvalResult:
    """
    输入：tenant/actor/tool/args/context
    输出：decision + reason_code + metadata
    """
    tid = str(tenant_id or "").strip() or None
    pol, ver = (await _load_tenant_policy_snapshot(store=store, tenant_id=tid)) if tid else (None, None)
    return evaluate_tool_policy_snapshot(
        policy=pol,
        policy_version=ver,
        tenant_id=tid,
        actor_id=actor_id,
        actor_role=actor_role,
        tool_name=tool_name,
        tool_args=tool_args,
    )


def _is_prod() -> bool:
    return os.getenv("AIPLAT_ENV", "").lower() in {"prod", "production"}


async def evaluate_mcp_server(
    *,
    store: Any,
    tenant_id: Optional[str],
    actor_id: Optional[str],
    actor_role: Optional[str],
    server_name: str,
    transport: str,
    server_metadata: Optional[Dict[str, Any]] = None,
) -> PolicyEvalResult:
    """
    MCP runtime 策略：默认 prod 禁用 stdio，除非 tenant policy 或 server metadata 显式允许。
    """
    tid = str(tenant_id or "").strip() or None
    pol, ver = (await _load_tenant_policy_snapshot(store=store, tenant_id=tid)) if tid else (None, None)
    p0 = pol if isinstance(pol, dict) else {}
    mp = p0.get("mcp_policy") if isinstance(p0.get("mcp_policy"), dict) else {}

    prod_allowed = mp.get("prod_allowed")
    if prod_allowed is None and isinstance(server_metadata, dict):
        prod_allowed = server_metadata.get("prod_allowed")

    if _is_prod() and str(transport) == "stdio" and not bool(prod_allowed):
        return PolicyEvalResult(
            decision=PolicyDecision.DENY,
            reason_code="MCP_STDIO_DENIED_IN_PROD",
            reason="prod policy denies stdio MCP server",
            tenant_id=tid,
            policy_version=ver,
            matched_rule="mcp_policy.prod_allowed",
            metadata={"server": server_name, "transport": transport, "actor_id": actor_id, "actor_role": actor_role},
        )

    return PolicyEvalResult(
        decision=PolicyDecision.ALLOW,
        reason_code="ALLOW",
        reason="allowed",
        tenant_id=tid,
        policy_version=ver,
        matched_rule=None,
        metadata={"server": server_name, "transport": transport, "actor_id": actor_id, "actor_role": actor_role},
    )
