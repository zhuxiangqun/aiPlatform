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


class AgentUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class SkillCreateRequest(BaseModel):
    name: str
    description: str = ""
    category: str = "general"
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)


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
