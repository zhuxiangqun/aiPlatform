"""Response models for the FDE workbench endpoints (workbench.py)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class CapabilityItem(BaseModel): id: str; name: str; desc: str = ""; icon: str = ""
class TaskSubmitResponse(BaseModel): run_id: str; status: str; spec_id: str = ""
class TaskFeedbackResponse(BaseModel): run_id: str; rating: int; recorded: bool = True
class TrainingStatusResponse(BaseModel): status: str = ""; model: str = ""; dataset: str = ""; error: Optional[str] = None
class SkillInstallResponse(BaseModel): status: str; skill: str; source: str = ""
class SeedDemoResponse(BaseModel): seeded: int; specs: List[str] = Field(default_factory=list); note: str = ""
class BatchResultItem(BaseModel): spec_id: str; status: str; error: Optional[str] = None
class BatchMarkStableResponse(BaseModel): total: int; stable: int; results: List[BatchResultItem] = Field(default_factory=list)


# ── Request models ──────────────────────────────────────────────────

class TaskSubmitRequest(BaseModel):
    description: str
    capability: str = "general"
    spec_id: str = ""
    run_id: str = ""


class TaskFeedbackRequest(BaseModel):
    rating: int = 0
    action: str = "useful"


class SpecCreateRequest(BaseModel):
    spec_id: str
    content: dict = Field(default_factory=dict)
    created_by: str = "developer"


class SpecReviseRequest(BaseModel):
    content: dict
    trigger: str = "manual"
    trigger_detail: str = ""
    created_by: str = "developer"
    affected_stages: Optional[List[int]] = None
    re_execute: bool = False


class SkillInstallRequest(BaseModel):
    url: str


class SpecPromotionRequest(BaseModel):
    target_platform: str = "platform"
    reason: str = ""


class SpecApproveRequest(BaseModel):
    approver: str = "admin"
    note: str = ""


class SpecRejectRequest(BaseModel):
    approver: str = "admin"
    reason: str = ""
