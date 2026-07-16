"""
Role-based access control — route-level permissions.

8 system roles with per-route access defined by management screen.
Role resolution: X-AIPLAT-ROLE header (from Gateway) → env var → default.

METHOD RESTRICTION: ROUTE_PERMISSIONS does NOT differentiate HTTP methods.
When adding read-only roles (viewer), only assign paths whose ALL endpoints
are safe for that role. Do NOT assign routes containing POST/PUT/DELETE
endpoints unless protected by an additional middleware layer.
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
