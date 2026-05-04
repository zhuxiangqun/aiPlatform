from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConversationScope(BaseModel):
    collection_id: str = "default"
    doc_ids: List[str] = Field(default_factory=list)
    version: int = 1
    scope_hash: Optional[str] = None


class ConversationProfile(BaseModel):
    citation_required: bool = True
    answer_style: str = "concise"
    language: str = "zh-CN"


class ConversationCreateRequest(BaseModel):
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    title: Optional[str] = None
    scope: Optional[ConversationScope] = None
    profile: Optional[ConversationProfile] = None


class ConversationSummary(BaseModel):
    session_id: str
    title: str
    updated_at: Optional[float] = None
    scope: ConversationScope


class ConversationDetail(BaseModel):
    session_id: str
    title: str
    scope: ConversationScope
    profile: ConversationProfile
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class ConversationScopeUpdateRequest(BaseModel):
    collection_id: Optional[str] = None
    doc_ids: Optional[List[str]] = None
    version: Optional[int] = None


class ConversationQueryOptions(BaseModel):
    citation_required: bool = True
    max_citations: int = 8
    top_k: int = 8
    language: str = "zh-CN"


class ConversationQueryRequest(BaseModel):
    message: str
    user_id: Optional[str] = None
    scope_override: Optional[ConversationScope] = None
    options: Optional[ConversationQueryOptions] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationQueryAccepted(BaseModel):
    run_id: str
    status: str
    session_id: str
    scope_applied: ConversationScope
