"""
Agent API schemas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentCreateRequest(BaseModel):
    name: str
    agent_type: str = "base"
    config: Dict[str, Any] = Field(default_factory=dict)
    skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    mcp_ids: List[str] = Field(default_factory=list)
    workflow_ids: List[str] = Field(default_factory=list)
    agent_ids: List[str] = Field(default_factory=list)
    memory_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    trigger_conditions: Optional[List[str]] = None
    permissions: Optional[List[str]] = None


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    mcp_ids: Optional[List[str]] = None
    workflow_ids: Optional[List[str]] = None
    agent_ids: Optional[List[str]] = None
    memory_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    trigger_conditions: Optional[List[str]] = None
    permissions: Optional[List[str]] = None


class AgentOutput(BaseModel):
    """Structured agent execution output — compatible with Browser Use ActionResult pattern."""
    success: bool = True
    extracted_content: Optional[str] = Field(default=None, description="Structured data extracted by the agent")
    long_term_memory: Optional[str] = Field(default=None, description="Information to remember across steps")
    is_done: bool = Field(default=False, description="Whether the agent has completed the task")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    attachments: List[str] = Field(default_factory=list, description="File paths, screenshots, etc.")


class AgentAutoFillRequest(BaseModel):
    """Request for AI-powered agent creation auto-fill."""
    name: str = ""
    description: str = ""
    role_definition: Optional[Dict[str, Any]] = None
    async_mode: bool = False  # 异步模式：立即返回 task_id，后台执行
    metadata: Optional[Dict[str, Any]] = None


class RoleDefinitionResponse(BaseModel):
    """AI-generated role definition based on functional description."""
    role_name: str = ""
    responsibilities: List[str] = Field(default_factory=list)
    scenarios: List[str] = Field(default_factory=list)
    required_capabilities: List[str] = Field(default_factory=list)
    workflow_hint: str = ""
    reasoning: str = ""


class AgentAutoFillResponse(BaseModel):
    """AI-suggested agent configuration based on functional description."""
    agent_type: str = "base"
    config: Dict[str, Any] = Field(default_factory=dict)
    skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    mcp_ids: List[str] = Field(default_factory=list)
    missing_skills: List[Dict[str, str]] = Field(default_factory=list)
    missing_tools: List[Dict[str, str]] = Field(default_factory=list)
    missing_mcps: List[Dict[str, str]] = Field(default_factory=list)
    agent_ids: List[str] = Field(default_factory=list)
    memory_config: Dict[str, Any] = Field(default_factory=dict)
    sop_text: str = ""
    reasoning: str = ""
    workflow_ids: List[str] = Field(default_factory=list)
    trigger_conditions: List[str] = Field(default_factory=list)
    template_id: str = ""  # recommended prompt app template
    stages: List[Dict[str, Any]] = Field(default_factory=list)  # v4.0 pipeline stages
    # Async mode fields
    task_id: Optional[str] = None
    status: Optional[str] = None


class AgentAutoFillBatchRequest(BaseModel):
    names: List[str] = Field(default_factory=list, min_length=1, max_length=50)


class AgentAutoFillBatchResponse(BaseModel):
    results: Dict[str, AgentAutoFillResponse] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)

