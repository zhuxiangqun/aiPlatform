"""
Harness management schemas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HookCreateRequest(BaseModel):
    name: str
    hook_type: str
    config: Dict[str, Any] = Field(default_factory=dict)


class HookUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class CoordinatorCreateRequest(BaseModel):
    pattern: str
    agents: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)


class FeedbackConfigUpdateRequest(BaseModel):
    local: Optional[bool] = None
    push: Optional[bool] = None
    prod: Optional[bool] = None

