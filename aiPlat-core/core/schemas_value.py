"""Response models for the value/goal tracking endpoints (value.py)."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TrendPoint(BaseModel):
    """TrendPoint。"""
    timestamp: str = ""
    value: float = 0.0


class BusinessGoalItem(BaseModel):
    """BusinessGoalItem。"""
    goal_id: str
    description: str
    target_metric: str = ""
    baseline_value: float = 0.0
    target_value: float = 0.0
    current_value: float = 0.0
    progress_pct: float = 0.0
    achieved: bool = False
    owner: str = ""
    period: str = ""


class BusinessGoalCreateResponse(BaseModel):
    """BusinessGoalCreateResponse。"""
    goal_id: str
    status: str = "created"


class BusinessGoalUpdateResponse(BaseModel):
    """BusinessGoalUpdateResponse。"""
    goal_id: str
    current_value: float
    progress_pct: float
    achieved: bool


class BusinessGoalTrendResponse(BaseModel):
    """BusinessGoalTrendResponse。"""
    goal_id: str
    trend: List[TrendPoint] = Field(default_factory=list)
    current_progress_pct: float = 0.0


class StrategyStatusResponse(BaseModel):
    """StrategyStatusResponse。"""
    params: Dict[str, Any] = Field(default_factory=dict)
    context: str = ""
    goals_count: int = 0


class GoalSourceResponse(BaseModel):
    """GoalSourceResponse。"""
    goal_id: str
    collection_method: str = ""
    linked_agent: str = ""
    category: str = ""
    status: str = ""


# ── Request models ──────────────────────────────────────────────────

class GoalCreateRequest(BaseModel):
    """GoalCreateRequest。"""
    goal_id: str
    description: str = ""
    target_metric: str = ""
    baseline_value: float = 0.0
    target_value: float = 0.0
    owner: str = ""
    period: str = ""


class GoalUpdateRequest(BaseModel):
    """GoalUpdateRequest。"""
    current_value: float


class GoalSourceConfigRequest(BaseModel):
    """GoalSourceConfigRequest。"""
    goal_id: str
    collection_method: str = "manual"
    linked_agent: str = ""
    category: str = ""
