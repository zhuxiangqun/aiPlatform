"""Response models for the role management endpoints (roles.py)."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RoleAgentItem(BaseModel):
    agent_id: str
    role: str
    model: str = ""
    reflection_enabled: bool = False
    last_updated: str = ""
    agent_type: Optional[str] = None
    description: Optional[str] = None


class RoleAgentUpdateResponse(BaseModel):
    agent_id: str
    role: str
    model: str = ""
    reflection_enabled: bool = False
    config: Optional[Dict[str, Any]] = None


class RoleMetricsResponse(BaseModel):
    employee: Dict[str, Any] = Field(default_factory=dict)
    guard: Dict[str, Any] = Field(default_factory=dict)
    advisor: Dict[str, Any] = Field(default_factory=dict)
    orchestrator: Dict[str, Any] = Field(default_factory=dict)


class RoleStrategyOverrideResponse(BaseModel):
    agent_id: str
    mode: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)


# ── Request models ──────────────────────────────────────────────────

class RoleAgentUpdateRequest(BaseModel):
    role: str = "employee"
    config: Dict[str, Any] = Field(default_factory=dict)


class RoleStrategyOverrideRequest(BaseModel):
    agent_id: str = ""
    mode: str = "normal"
