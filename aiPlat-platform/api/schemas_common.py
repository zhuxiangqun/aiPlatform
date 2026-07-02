"""Shared Pydantic response models for aiPlat-platform API endpoints.

Provides common base types plus platform-specific response models.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PlatformResponse(BaseModel):
    """Standard platform success/error response."""
    ok: bool = True
    message: str = ""
    error: Optional[str] = None


class PaginatedResponse(BaseModel):
    """Standard paginated response."""
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    limit: int = 100
    offset: int = 0


class StatusResponse(BaseModel):
    """Simple status-only response."""
    status: str = "ok"
    message: str = ""


class IdResponse(BaseModel):
    """Response containing a single ID."""
    id: str = ""
    session_id: str = ""
    project_id: str = ""
    run_id: str = ""


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = ""
    uptime_seconds: float = 0.0
