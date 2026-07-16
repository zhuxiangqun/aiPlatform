"""
DEPRECATED — Permission config canonical location: aiPlat-platform/auth/schemas_policy.py

This module provides backwards compatibility by importing from the canonical
auth.schemas_policy and re-exporting for existing callers.

New code MUST import from: auth.schemas_policy
This module will be removed in v2.2.
"""
import os as _os
import sys as _sys
import warnings

warnings.warn(
    "core.schemas_policy is deprecated. Use auth.schemas_policy instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Ensure aiPlat-platform/auth is on sys.path for the canonical import
_project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_platform_dir = _os.path.join(_project_root, 'aiPlat-platform')
if _platform_dir not in _sys.path:
    _sys.path.insert(0, _platform_dir)

from auth.schemas_policy import (  # noqa: E402
    SystemRole, ROUTE_PERMISSIONS, SIDEBAR_MENUS, METHOD_RESTRICTIONS,
)

__all__ = ["SystemRole", "ROUTE_PERMISSIONS", "SIDEBAR_MENUS", "METHOD_RESTRICTIONS"]
