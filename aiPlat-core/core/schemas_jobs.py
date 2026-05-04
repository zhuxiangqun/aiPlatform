"""
Jobs / cron schemas.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    name: str
    kind: str = "agent"  # agent|skill|tool|graph
    target_id: str
    cron: str = "* * * * *"
    enabled: bool = True
    timezone: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[Dict[str, Any]] = None
    delivery: Optional[Dict[str, Any]] = None


class JobUpdateRequest(BaseModel):
    name: Optional[str] = None
    cron: Optional[str] = None
    enabled: Optional[bool] = None
    timezone: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, Any]] = None
    delivery: Optional[Dict[str, Any]] = None

