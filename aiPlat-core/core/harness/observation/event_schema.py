"""Typed syscall event schema — validates events at entry point."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SyscallEvent(BaseModel):
    """A single syscall audit event — LLM call, tool call, skill call, routing."""
    id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    run_id: Optional[str] = None
    tenant_id: Optional[str] = None
    kind: str = ""
    name: str = ""
    status: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    args: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="args_json")
    result: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="result_json")
    error: Optional[str] = None
    error_code: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    approval_request_id: Optional[str] = None
    created_at: Optional[float] = None

    class Config:
        populate_by_name = True
        extra = "allow"
