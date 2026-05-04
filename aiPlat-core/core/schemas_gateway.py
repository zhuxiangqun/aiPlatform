"""
Gateway / channels schemas.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class GatewayExecuteRequest(BaseModel):
    channel: str = "default"
    kind: str = "agent"  # agent|skill|tool|graph
    target_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    # Optional external identity (for pairing). If user_id/session_id not provided,
    # core will try to resolve via gateway_pairings.
    channel_user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[Dict[str, Any]] = None

