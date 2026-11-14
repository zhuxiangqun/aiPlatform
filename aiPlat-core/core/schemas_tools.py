"""
Tool binding / trigger schemas.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ToolBindRequest(BaseModel):
    """ToolBindRequest。"""
    tool_ids: List[str]


class TriggerConditionsUpdateRequest(BaseModel):
    """TriggerConditionsUpdateRequest。"""
    trigger_conditions: List[str] = Field(default_factory=list)


class TriggerTestRequest(BaseModel):
    """TriggerTestRequest。"""
    input: str

