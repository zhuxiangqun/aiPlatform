"""Shared Pydantic response models for aiPlat-core API endpoints.

Provides common base types so routers don't need per-endpoint model definitions.
Use `response_model=Dict[str, Any]` for complex/dynamic responses that don't fit
a fixed schema.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypeVar, Generic
from pydantic import BaseModel, Field


T = TypeVar("T")


class CoreResponse(BaseModel, Generic[T]):
    """Standard success response wrapper."""
    ok: bool = True
    data: Optional[T] = None
    error: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response."""
    items: List[T] = Field(default_factory=list)
    total: int = 0
    limit: int = 100
    offset: int = 0


class StatusResponse(BaseModel):
    """Simple status-only response (health check, ack, etc.)."""
    status: str = "ok"
    message: str = ""


class IdResponse(BaseModel):
    """Response containing a single ID (session_id, run_id, project_id, etc.)."""
    id: str


class CountResponse(BaseModel):
    """Response containing a count."""
    count: int = 0
