"""
Backwards-compatible exports for RBAC helpers.

New code should import from:
- core.api.deps.actor import actor_from_http
- core.api.deps.guard import rbac_guard
"""

from __future__ import annotations

from .actor import actor_from_http
from .guard import rbac_guard

__all__ = ["actor_from_http", "rbac_guard"]
