"""
aiPlat-core Pydantic Schemas

统一管理所有 API 请求/响应模型，消除重复定义。
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class AgentCreateRequest(BaseModel):
    name: str
    agent_type: str = "base"
    config: Dict[str, Any] = Field(default_factory=dict)
    skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    memory_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    memory_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class SkillCreateRequest(BaseModel):
    name: str
    description: str = ""
    category: str = "general"
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    template: Optional[str] = None
    sop: Optional[str] = None


class SkillUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class SkillExecuteRequest(BaseModel):
    input: Dict[str, Any] = Field(default_factory=dict)
    context: Optional[Dict[str, Any]] = None
    mode: str = "inline"
    # Roadmap-2: runtime governance hints (e.g. toolset).
    # This is optional and forward-compatible.
    options: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------
# Roadmap-3: Jobs/Cron
# ---------------------------------------------------------------------


class JobCreateRequest(BaseModel):
    name: str
    kind: str = "agent"  # agent|skill|tool|graph
    target_id: str
    cron: str = "* * * * *"
    enabled: bool = True
    timezone: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[Dict[str, Any]] = None
    delivery: Optional[Dict[str, Any]] = None


class JobUpdateRequest(BaseModel):
    name: Optional[str] = None
    cron: Optional[str] = None
    enabled: Optional[bool] = None
    timezone: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, Any]] = None
    delivery: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------
# Roadmap-3: Gateway / Channels (minimal)
# ---------------------------------------------------------------------


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


class SkillPackCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    manifest: Dict[str, Any] = Field(default_factory=dict)


class SkillPackUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    manifest: Optional[Dict[str, Any]] = None


class SkillPackPublishRequest(BaseModel):
    version: str


class SkillPackInstallRequest(BaseModel):
    version: Optional[str] = None
    scope: str = "workspace"  # engine|workspace
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------
# Packages Registry (publish/install)
# ---------------------------------------------------------------------


class PackagePublishRequest(BaseModel):
    version: str
    # Optional approval gate
    require_approval: bool = False
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class PackageInstallRequest(BaseModel):
    package_name: Optional[str] = None  # allow body override; path param is authoritative
    version: Optional[str] = None  # if omitted, install from filesystem package (latest)
    scope: str = "workspace"  # engine|workspace (target scope for apply)
    allow_overwrite: bool = False
    metadata: Optional[Dict[str, Any]] = None
    # Optional approval gate
    require_approval: bool = False
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


# ---------------------------------------------------------------------
# Onboarding (core-side)
# ---------------------------------------------------------------------


class OnboardingDefaultLLMRequest(BaseModel):
    adapter_id: str
    model: str
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingInitTenantRequest(BaseModel):
    tenant_id: str = "default"
    tenant_name: Optional[str] = None
    init_policies: bool = True
    strict_tool_approval: bool = True  # if true, approval_required_tools=['*']
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingAutosmokeConfigRequest(BaseModel):
    enabled: bool = True
    enforce: bool = True
    webhook_url: Optional[str] = None
    dedup_seconds: Optional[int] = None
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class LongTermMemoryAddRequest(BaseModel):
    user_id: Optional[str] = None
    key: Optional[str] = None
    content: str
    metadata: Optional[Dict[str, Any]] = None


class LongTermMemorySearchRequest(BaseModel):
    user_id: Optional[str] = None
    query: str
    limit: int = 10


class MessageCreateRequest(BaseModel):
    role: str
    content: str


class SessionCreateRequest(BaseModel):
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class CollectionCreateRequest(BaseModel):
    name: str
    description: str = ""


class DocumentCreateRequest(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


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


class HookCreateRequest(BaseModel):
    name: str
    hook_type: str
    config: Dict[str, Any] = Field(default_factory=dict)


class HookUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class CoordinatorCreateRequest(BaseModel):
    pattern: str
    agents: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)


class FeedbackConfigUpdateRequest(BaseModel):
    local: Optional[bool] = None
    push: Optional[bool] = None
    prod: Optional[bool] = None


class SkillBindRequest(BaseModel):
    skill_ids: List[str]


class ToolBindRequest(BaseModel):
    tool_ids: List[str]


class TriggerConditionsUpdateRequest(BaseModel):
    trigger_conditions: List[str] = Field(default_factory=list)


class TriggerTestRequest(BaseModel):
    input: str
