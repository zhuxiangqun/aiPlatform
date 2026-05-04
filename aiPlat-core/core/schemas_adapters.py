"""
LLM adapter schemas.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AdapterCreateRequest(BaseModel):
    name: str
    provider: str
    api_key: str
    api_base_url: str
    description: str = ""
    organization_id: Optional[str] = None


class AdapterUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None


class ModelUpdateRequest(BaseModel):
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)

