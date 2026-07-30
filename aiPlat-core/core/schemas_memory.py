"""
Memory schemas.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class LongTermMemoryAddRequest(BaseModel):
    user_id: Optional[str] = None
    key: Optional[str] = None
    content: str
    metadata: Optional[Dict[str, Any]] = None


class LongTermMemorySearchRequest(BaseModel):
    user_id: Optional[str] = None
    query: str
    limit: int = 10


class LongTermMemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    key: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MessageCreateRequest(BaseModel):
    role: str
    content: str


class SessionCreateRequest(BaseModel):
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

