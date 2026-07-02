"""
Role-based access control — route-level permissions.

5 system roles with per-route access defined by management screen.
Role resolution: X-AIPLAT-ROLE header (from Gateway) → env var → default.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List


class SystemRole(str, Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    BUSINESS = "business"
    USER = "user"
    APPROVER = "approver"


# Route permissions: path prefix → allowed roles
ROUTE_PERMISSIONS: Dict[str, List[str]] = {
    # Admin-only
    "/system-overview":          ["admin"],
    "/onboarding":               ["admin"],
    "/value-center/roles":       ["admin"],
    "/value-center":             ["admin", "business"],  # ValueDashboard shared
    "/value-center/kpis":        ["admin", "business"],
    "/value-center/goals":       ["admin", "business"],
    "/platform":                 ["admin"],

    # Admin + Developer
    "/value-center/strategy":    ["admin", "developer"],
    "/value-center/training":    ["admin", "developer"],
    "/diagnostics":              ["admin", "developer"],
    "/finetune":                 ["admin", "developer"],
    "/infra":                    ["admin", "developer"],
    "/core":                     ["admin", "developer"],
    "/workspace":                ["admin", "developer"],
    "/api/core":                 ["admin", "developer"],  # API access

    # All roles (differ by operation)
    "/workbench":               ["admin", "developer", "business", "user"],
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
    "user": [
        "workbench", "app",
    ],
    "approver": [
        "approval", "workbench",
    ],
}
