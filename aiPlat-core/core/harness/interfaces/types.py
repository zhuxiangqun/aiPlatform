"""
Harness-level shared types. These are pure data types with no service dependencies,
so they can be imported from both harness (core/harness/) and apps (core/apps/)
without creating reverse dependencies.

Previously these enums lived in:
  - SpanStatus: core/services/trace_service.py (harness→services direction violation)
  - Permission: core/apps/tools/permission.py (not harness-accessible)
Both are now defined here as the single source of truth.
"""

from __future__ import annotations

from enum import Enum


class SpanStatus(str, Enum):
    """Span status enumeration — shared across trace_service and integration.py."""
    STARTED = "started"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class Permission(str, Enum):
    """Permission enum — shared across policy_gate, integration, and tool layer."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
