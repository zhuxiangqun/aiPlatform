"""
DEPRECATED — Permission config has moved to platform layer.

Platform is the sole authority for identity and permission (CLAUDE.md §5.2,
docs/architecture/system-architecture-contract.md). The canonical copy of
ROUTE_PERMISSIONS, SystemRole, SIDEBAR_MENUS, and METHOD_RESTRICTIONS now  # noqa: boundary
lives in:

    aiPlat-platform/auth/schemas_policy.py

This module provides a temporary duplicate for backward compatibility during
the v2.0→v2.1 transition. New code MUST import from the platform copy.

This module will be removed in v2.1 (scheduled: 2026-08).
"""
from __future__ import annotations

import warnings

warnings.warn(
    "Import from 'core.schemas_policy' is deprecated. "
    "Use 'platform.auth.schemas_policy' instead. "
    "This module will be removed in v2.1 (2026-08).",
    DeprecationWarning,
    stacklevel=2,
)

from enum import Enum
from typing import Dict, List


class SystemRole(str, Enum):  # noqa: boundary — transitional duplicate, v2.1 cleanup
    ADMIN = "admin"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    BUSINESS = "business"
    USER = "user"
    APPROVER = "approver"
    FDE = "fde"
    VIEWER = "viewer"


ROUTE_PERMISSIONS: Dict[str, List[str]] = {  # noqa: boundary — transitional duplicate, v2.1 cleanup
    "/system-overview":          ["admin"],
    "/onboarding":               ["admin"],
    "/value-center/roles":       ["admin"],
    "/value-center":             ["admin", "business", "fde"],
    "/value-center/kpis":        ["admin", "business"],
    "/value-center/goals":       ["admin", "business"],
    "/value-center/strategy":    ["admin", "developer"],
    "/value-center/training":    ["admin", "developer"],
    "/diagnostics":              ["admin", "developer", "operator", "fde"],
    "/finetune":                 ["admin", "developer"],
    "/infra":                    ["admin", "developer", "operator", "fde"],
    "/core":                     ["admin", "developer", "fde"],
    "/workspace":                ["admin", "developer", "fde"],
    "/api/core":                 ["admin", "developer"],
    "/platform":                 ["admin", "operator"],
    "/workbench":               ["admin", "developer", "operator", "business", "user", "fde", "viewer"],
    "/value-center/spec":       ["admin", "developer", "business", "approver"],
    "/app":                     ["admin", "user"],
    "/approval-center":         ["admin", "approver"],
}

SIDEBAR_MENUS: Dict[str, List[str]] = {  # noqa: boundary — transitional duplicate, v2.1 cleanup
    "admin": [
        "system-overview", "diagnostics", "onboarding",
        "infra", "core", "platform",
        "value", "workbench", "finetune", "approval",
    ],
    "developer": [
        "workbench", "value", "finetune",
        "core", "workspace", "diagnostics",
    ],
    "business": ["value", "workbench"],
    "operator": ["diagnostics", "infra", "platform", "workbench"],
    "user": ["workbench", "app"],
    "approver": ["approval", "workbench"],
    "fde": ["diagnostics", "infra", "core", "workspace", "value"],
    "viewer": ["workbench"],
}

METHOD_RESTRICTIONS: Dict[str, Dict[str, List[str]]] = {  # noqa: boundary — transitional duplicate, v2.1 cleanup
    "viewer": {},
}

__all__ = ["SystemRole", "ROUTE_PERMISSIONS", "SIDEBAR_MENUS", "METHOD_RESTRICTIONS"]  # noqa: boundary — transitional re-export
