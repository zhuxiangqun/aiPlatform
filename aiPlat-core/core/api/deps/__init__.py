"""
API dependencies facade.

Motivation: provide a stable import surface (reduce cross-module coupling and churn).
Prefer importing from `core.api.deps` instead of individual files.
"""

from __future__ import annotations

from .actor import actor_from_http
from .guard import rbac_guard

__all__ = ["actor_from_http", "rbac_guard"]

