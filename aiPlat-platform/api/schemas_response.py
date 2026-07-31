"""Pydantic response models for aiPlat-platform API endpoints.

These models enable OpenAPI schema generation, automatic response validation,
and client-side type guarantees for the platform layer's public REST API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Chat ──

class ChatSessionResponse(BaseModel):
    """POST /platform/chat/sessions"""
    session_id: str


class ChatReplyResponse(BaseModel):
    """POST /platform/chat/sessions/{session_id}/chat"""
    reply: str
    session_id: str
    messages: List[Dict[str, str]] = Field(default_factory=list)


class ChatSessionDetailResponse(BaseModel):
    """GET /platform/chat/sessions/{session_id}"""
    session_id: str
    agent_id: str = ""
    system_prompt: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    messages: List[Dict[str, str]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── Conversations ──

class ConversationScope(BaseModel):
    collection_id: str = "default"
    doc_ids: List[str] = Field(default_factory=list)
    version: int = 0
    scope_hash: str = ""


class ConversationProfile(BaseModel):
    citation_required: bool = False
    answer_style: str = "detailed"
    language: str = "zh-CN"


class ConversationResponse(BaseModel):
    """POST /platform/conversations, GET /platform/conversations/{session_id}"""
    session_id: str
    title: str = ""
    scope: ConversationScope = Field(default_factory=ConversationScope)
    profile: ConversationProfile = Field(default_factory=ConversationProfile)
    messages: List[Dict[str, str]] = Field(default_factory=list)
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    tenant_id: str = "default"
    user_id: str = ""


class ConversationListItem(BaseModel):
    session_id: str
    title: str = ""
    scope: ConversationScope = Field(default_factory=ConversationScope)
    updated_at: Optional[float] = None
    created_at: Optional[float] = None


class ConversationListResponse(BaseModel):
    """GET /platform/conversations"""
    items: List[ConversationListItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 100
    offset: int = 0


class ConversationScopeUpdateResponse(BaseModel):
    """PUT /platform/conversations/{session_id}/scope"""
    ok: bool = True
    scope: ConversationScope = Field(default_factory=ConversationScope)


class ConversationQueryResponse(BaseModel):
    """POST /platform/conversations/{session_id}/query"""
    answer: str = ""
    strategy: str = ""
    ok: bool = True
    session_id: str = ""
    scope_applied: Dict[str, Any] = Field(default_factory=dict)


# ── Approvals ──

class ApprovalListItem(BaseModel):
    request_id: str = ""
    user_id: str = ""
    operation: str = ""
    status: str = ""
    details: Any = None
    rule_id: str = ""
    rule_type: Optional[str] = None
    is_first_time: bool = False
    created_at: str = ""
    updated_at: str = ""
    expires_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ApprovalListResponse(BaseModel):
    """GET /platform/approvals"""
    items: List[ApprovalListItem] = Field(default_factory=list)
    total: int = 0


class ApprovalActionResponse(BaseModel):
    """POST /platform/approvals/{request_id}/approve|reject"""
    status: str
    request_id: str


# ── Builder ──

class ProjectListResponse(BaseModel):
    """GET /platform/builder/projects"""
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class ProjectStateResponse(BaseModel):
    """GET /platform/builder/projects/{id}/state"""
    project_id: str = ""
    phase: str = ""
    confirmed_prd: Optional[Dict[str, Any]] = None
    state: Dict[str, Any] = Field(default_factory=dict)
    runs: List[Dict[str, Any]] = Field(default_factory=list)


class PipelineStartResponse(BaseModel):
    """POST /platform/builder/projects/{id}/start"""
    project_id: str
    phase: str
    run_id: str
    state: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class TeamListResponse(BaseModel):
    """GET /platform/builder/teams"""
    teams: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class StatusResponse(BaseModel):
    """Generic typed response — replaces Dict[str, Any] / dict across all endpoints.
    
    Accepts any extra fields at runtime via model_config extra=allow.
    Use this instead of response_model=StatusResponse for proper OpenAPI schema generation.
    """
    model_config = {"extra": "allow", "protected_namespaces": ()}

    status: str = "ok"
    detail: str = ""
    message: str = ""


class IDResponse(BaseModel):
    """Response containing an entity ID — used by create endpoints."""
    model_config = {"extra": "allow", "protected_namespaces": ()}
    
    id: str = ""


class ListResponse(BaseModel):
    """Generic list wrapper."""
    model_config = {"extra": "allow", "protected_namespaces": ()}
    
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class CountResponse(BaseModel):
    """Simple count response."""
    model_config = {"extra": "allow", "protected_namespaces": ()}
    
    count: int = 0
    success: bool = True
