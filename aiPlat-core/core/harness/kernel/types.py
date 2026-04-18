"""
Kernel Types (Contracts) - Phase 1

This module defines the minimal execution contracts used by HarnessIntegration.execute().

NOTE: This is a Phase-1 implementation to support "single entry" migration.
It will be expanded and frozen in design doc phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


ExecutionKind = Literal["agent", "skill", "tool", "graph"]


@dataclass
class ExecutionRequest:
    """Kernel execution request (minimal)."""

    kind: ExecutionKind
    target_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    user_id: str = "system"
    session_id: str = "default"
    request_id: Optional[str] = None


@dataclass
class ExecutionResult:
    """Kernel execution result (minimal)."""

    ok: bool
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    # Roadmap-0: normalized error contract (backward compatible; payload may also carry error_detail).
    error_detail: Optional[Dict[str, Any]] = None
    http_status: int = 200
    trace_id: Optional[str] = None
    run_id: Optional[str] = None
