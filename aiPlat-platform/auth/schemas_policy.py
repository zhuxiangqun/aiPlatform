"""
Role-based access control — route-level permissions.

Platform layer is the SOLE AUTHORITY for identity and permission
parsing/issuing (docs/architecture/system-architecture-contract.md).
All route permissions, role definitions, and sidebar menu visibility
belong here — NOT in core.

8 system roles with per-route access defined by management screen.
Role resolution: X-AIPLAT-ROLE header (from Gateway) → env var → default.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List


class SystemRole(str, Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    BUSINESS = "business"
    USER = "user"
    APPROVER = "approver"
    FDE = "fde"
    VIEWER = "viewer"


# Route permissions: path prefix → allowed roles
ROUTE_PERMISSIONS: Dict[str, List[str]] = {
    # Admin-only
    "/system-overview":          ["admin"],
    "/onboarding":               ["admin"],
    "/value-center/roles":       ["admin"],
    "/value-center":             ["admin", "business", "fde"],  # ValueDashboard shared
    "/value-center/kpis":        ["admin", "business"],
    "/value-center/goals":       ["admin", "business"],

    # Admin + Developer
    "/value-center/strategy":    ["admin", "developer"],
    "/value-center/training":    ["admin", "developer"],

    # Admin + Developer + Operator + FDE
    "/diagnostics":              ["admin", "developer", "operator", "fde"],
    "/finetune":                 ["admin", "developer"],
    "/infra":                    ["admin", "developer", "operator", "fde"],
    "/core":                     ["admin", "developer", "fde"],
    "/workspace":                ["admin", "developer", "fde"],
    "/api/core":                 ["admin", "developer"],  # API access

    # Admin + Operator
    "/platform":                 ["admin", "operator"],

    # All roles
    "/workbench":               ["admin", "developer", "operator", "business", "user", "fde", "viewer"],
    "/value-center/spec":       ["admin", "developer", "business", "approver"],

    # User
    "/app":                     ["admin", "user"],

    # Approver
    "/approval-center":         ["admin", "approver"],
}

# Sidebar visibility: what menu groups each role sees
SIDEBAR_MENUS: Dict[str, List[str]] = {
    "admin": [
        "system-overview", "diagnostics", "onboarding",
        "infra", "core", "platform",
        "value", "workbench", "finetune", "approval",
    ],
    "developer": [
        "workbench", "value", "finetune",
        "core", "workspace", "diagnostics",
    ],
    "business": [
        "value", "workbench",
    ],
    "operator": [
        "diagnostics", "infra", "platform", "workbench",
    ],
    "user": [
        "workbench", "app",
    ],
    "approver": [
        "approval", "workbench",
    ],
    "fde": [
        "diagnostics", "infra", "core", "workspace", "value",
    ],
    "viewer": [
        "workbench",
    ],
}

# Per-role HTTP method restrictions.
# For roles not listed here, all methods are allowed on permitted routes.
# For listed roles, only the specified methods are allowed.
METHOD_RESTRICTIONS: Dict[str, Dict[str, List[str]]] = {
    "viewer": {},
    # Example future use:
    # "viewer": {
    #     "/workbench": ["GET", "HEAD", "OPTIONS"],
    #     "/api/v1/agents": ["GET"],
    # },
    # "operator": {
    #     "/core/agents": ["GET"],
    # },
}


# ════════════════════════════════════════════════════════════════
# P1-A6: ManagedPolicy — 企业远程托管策略 (Claude Code 借鉴)
#
# managed: true 的策略项由企业管理员远程强制，本地 user policy 不可覆盖。
# PolicyGate 读策略时优先 managed 项。
# ════════════════════════════════════════════════════════════════

class ManagedPolicy:
    """Enterprise-managed policy entry (server-mandated, locally non-overridable).

    Args:
        scope: 策略作用域 (tenant | global)
        key: 策略键 (model_whitelist / sandbox_required / max_tools ...)
        value: 策略值
        managed: 是否托管 (True → 本地不可覆盖)
        source: 托管来源 (默认 "enterprise-admin")
    """

    def __init__(self, scope: str = "tenant", key: str = "",
                 value: object = None, managed: bool = True,
                 source: str = "enterprise-admin"):
        self.scope = scope
        self.key = key
        self.value = value
        self.managed = managed
        self.source = source

    @property
    def is_managed(self) -> bool:
        return self.managed

    def to_dict(self) -> Dict:
        return {
            "scope": self.scope,
            "key": self.key,
            "value": self.value,
            "managed": self.managed,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ManagedPolicy":
        return cls(
            scope=str(data.get("scope", "tenant")),
            key=str(data.get("key", "")),
            value=data.get("value"),
            managed=bool(data.get("managed", True)),
            source=str(data.get("source", "enterprise-admin")),
        )


def merge_managed_policy(local: Dict, managed: Dict) -> Dict:
    """Merge managed policy over local policy — managed keys win.

    Local policy may only relax keys NOT marked managed.
    """
    merged = dict(local or {})
    for key, val in (managed or {}).items():
        if isinstance(val, dict) and val.get("managed"):
            merged[key] = val.get("value", merged.get(key))
    return merged
