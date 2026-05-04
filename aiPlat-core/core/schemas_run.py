"""
Run contract schemas (v2).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel


class RunStatus(str, Enum):
    accepted = "accepted"
    running = "running"
    waiting_approval = "waiting_approval"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"
    timeout = "timeout"


class RunError(BaseModel):
    code: str
    message: str
    detail: Optional[Dict[str, Any]] = None


class RunSummary(BaseModel):
    ok: bool
    run_id: str
    trace_id: Optional[str] = None
    status: RunStatus
    output: Optional[Any] = None
    error: Optional[RunError] = None
    # Keep extra fields for forward/backward compat
    metadata: Optional[Dict[str, Any]] = None

