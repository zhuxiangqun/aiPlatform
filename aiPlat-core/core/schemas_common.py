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


class DeleteResponse(BaseModel):
    """Response for delete operations."""
    deleted: bool = True
    id: str = ""
    message: str = ""


class ListResponse(BaseModel, Generic[T]):
    """Simple unwrapped list response."""
    items: List[T] = Field(default_factory=list)


class MessageResponse(BaseModel):
    """Response with a status message and optional detail."""
    ok: bool = True
    message: str = Field(default="")
    detail: Optional[Dict[str, Any]] = None


class DictResponse(BaseModel):
    """Typed dict wrapper for key-value responses."""
    data: Dict[str, Any] = Field(default_factory=dict)


class IdNameResponse(BaseModel):
    """Response with ID + display name."""
    id: str
    name: str = ""


class WikiPageResponse(BaseModel):
    """Response for wiki page operations (create/update/delete)."""
    title: str
    status: str = "ok"
    path: str = ""
    auto_links: List[str] = Field(default_factory=list)


class WikiDeleteAllResponse(BaseModel):
    """Response for wiki delete-all operation."""
    deleted: int = 0
    message: str = ""


class ErrorDetail(BaseModel):
    """Structured error detail."""
    code: str = ""
    message: str = ""
    details: Optional[Dict[str, Any]] = None


class EnvInfoResponse(BaseModel):
    """Environment/info response."""
    version: str = ""
    python_version: str = ""
    env: Dict[str, Any] = Field(default_factory=dict)
