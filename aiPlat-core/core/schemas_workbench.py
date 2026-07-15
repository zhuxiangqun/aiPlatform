"""Response models for the FDE workbench endpoints (workbench.py)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class CapabilityItem(BaseModel): id: str; name: str; desc: str = ""; icon: str = ""
class TaskSubmitResponse(BaseModel): run_id: str; status: str; spec_id: str = ""
class TaskFeedbackResponse(BaseModel): run_id: str; rating: int; recorded: str = ""
class TrainingStatusResponse(BaseModel): status: str = ""; model: str = ""; dataset: str = ""; error: Optional[str] = None
class SkillInstallResponse(BaseModel): status: str; skill: str; source: str = ""
class SeedDemoResponse(BaseModel): seeded: int; specs: List[str] = Field(default_factory=list); note: str = ""
class BatchResultItem(BaseModel): spec_id: str; status: str; error: Optional[str] = None
class BatchMarkStableResponse(BaseModel): total: int; stable: int; results: List[BatchResultItem] = Field(default_factory=list)
