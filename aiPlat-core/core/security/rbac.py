"""
RBAC（最小企业权限模型） - PR-05

目标：
- 在 core 层将“谁能执行什么”收敛为强约束（tenant + actor + role）
- 先提供最小可用的角色模型与 action 权限表，后续可扩展为 policy-as-code
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class RBACDecision:
    allowed: bool
    reason: str


def normalize_role(role: Optional[str]) -> str:
    r = str(role or "").strip().lower()
    if not r:
        return "viewer"
    if r in {"admin", "operator", "developer", "viewer"}:
        return r
    # 兼容历史/扩展角色：未知视为 viewer
    return "viewer"


def check_permission(*, actor_role: Optional[str], action: str, resource_type: str) -> RBACDecision:
    """
    最小权限矩阵（可按需要扩展）：
    - admin：全权限
    - operator：可执行/可审批，但不能改 policy
    - developer：可执行（agent/skill/tool/graph），但不能审批、不能改 policy
    - viewer：只读（禁止执行/审批/写入）
    """
    role = normalize_role(actor_role)
    a = str(action or "").strip().lower()
    rt = str(resource_type or "").strip().lower()

    if role == "admin":
        return RBACDecision(True, "admin_allow")

    # execute*
    if a == "execute" and rt in {"agent", "skill", "tool", "graph", "gateway"}:
        if role in {"operator", "developer"}:
            return RBACDecision(True, f"{role}_allow_execute")
        return RBACDecision(False, "viewer_denied_execute")

    # approvals
    if a in {"approve", "reject"} and rt in {"approval_request", "approval"}:
        if role in {"operator"}:
            return RBACDecision(True, "operator_allow_approval")
        return RBACDecision(False, f"{role}_denied_approval")

    # run resume (wait auto-resume)
    if a in {"resume", "auto_resume"} and rt in {"run"}:
        if role in {"operator"}:
            return RBACDecision(True, "operator_allow_resume")
        return RBACDecision(False, f"{role}_denied_resume")

    # run redo (checkpoint reject -> redo)
    if a in {"redo", "rerun"} and rt in {"run"}:
        if role in {"operator"}:
            return RBACDecision(True, "operator_allow_redo")
        return RBACDecision(False, f"{role}_denied_redo")

    # run updates (events: checkpoint/join/workflow annotations)
    if a in {"update", "write"} and rt in {"run"}:
        if role in {"operator", "developer"}:
            return RBACDecision(True, f"{role}_allow_run_update")
        return RBACDecision(False, f"{role}_denied_run_update")

    # tenant policy / governance writes
    if a in {"policy_upsert", "policy_delete"} and rt in {"tenant_policy", "policy"}:
        return RBACDecision(False, f"{role}_denied_policy_write")

    # fallback: operator/developer only read
    if a in {"read", "list", "get"}:
        return RBACDecision(True, "read_allow")

    return RBACDecision(False, f"{role}_denied_{a}_{rt}")


def mode() -> str:
    """
    AIPLAT_RBAC_MODE:
    - warn（默认）：记录审计但不阻断
    - enforced：返回 403
    """
    return str(__import__("os").getenv("AIPLAT_RBAC_MODE", "warn")).strip().lower() or "warn"


def should_enforce() -> bool:
    return mode() in {"enforced", "enforce", "1", "true", "yes", "y"}


def should_warn() -> bool:
    return not should_enforce()
