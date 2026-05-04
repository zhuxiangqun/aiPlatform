"""
Evaluation / evidence / policy schemas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AutoEvalStep(BaseModel):
    tool: str
    args: Optional[Dict[str, Any]] = None
    tag: Optional[str] = None


class AutoEvalRequest(BaseModel):
    evaluator: str = "auto-llm"
    thresholds: Optional[Dict[str, Any]] = None
    enforce_gate: bool = False
    extra: Optional[Dict[str, Any]] = None
    policy: Optional[Dict[str, Any]] = None
    project_id: Optional[str] = None
    url: Optional[str] = None
    steps: Optional[List[AutoEvalStep]] = None
    expected_tags: Optional[List[str]] = None
    tag_expectations: Optional[Dict[str, Any]] = None
    tag_template: Optional[str] = None
    base_evidence_pack_id: Optional[str] = None

    class Config:
        extra = "allow"


class UpsertEvaluationPolicyRequest(BaseModel):
    policy: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class UpsertProjectEvaluationPolicyRequest(BaseModel):
    policy: Dict[str, Any] = Field(default_factory=dict)
    mode: str = "merge"  # merge|replace

    class Config:
        extra = "allow"


class EvidenceDiffRequest(BaseModel):
    base_evidence_pack_id: str
    new_evidence_pack_id: str

    class Config:
        extra = "allow"

