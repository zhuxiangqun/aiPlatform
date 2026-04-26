"""
aiPlat-core Pydantic Schemas

统一管理所有 API 请求/响应模型，消除重复定义。
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


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
    # v2: name = display_name；skill_id 可选（不填则由 name 派生）
    name: str
    skill_id: Optional[str] = None
    display_name: Optional[str] = None
    description: str = ""
    category: str = "general"
    version: Optional[str] = None
    status: Optional[str] = None
    skill_kind: Optional[str] = None  # rule|executable
    permissions: Optional[List[str]] = None
    trigger_conditions: Optional[List[str]] = None
    decision_tree: Optional[List[Dict[str, Any]]] = None
    resources: Optional[Dict[str, Any]] = None

    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    template: Optional[str] = None
    sop: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


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
# Auto Eval / Evidence / Policy (Phase Eval)
# ---------------------------------------------------------------------


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


# ---------------------------------------------------------------------
# Roadmap: Skills Installer (OpenCode-style distribution/installer)
# ---------------------------------------------------------------------


class SkillInstallerSourceType(str, Enum):
    git = "git"   # git clone url + ref
    path = "path"  # local directory path on server
    zip = "zip"   # local zip file path on server


class SkillInstallerInstallRequest(BaseModel):
    scope: str = "workspace"  # workspace only (production safe); engine is not recommended
    source_type: SkillInstallerSourceType = SkillInstallerSourceType.git
    # For git:
    url: Optional[str] = None
    ref: Optional[str] = None  # required for git (tag/commit SHA)
    # For path/zip:
    path: Optional[str] = None
    # Optional: install a single skill (by directory name or frontmatter name)
    skill_id: Optional[str] = None
    # Optional: subdir inside repo/path that contains skills
    subdir: Optional[str] = None
    auto_detect_subdir: bool = True
    allow_overwrite: bool = False
    # Optional guard: require explicit confirmation before mutating filesystem
    confirm: bool = False
    # plan_id returned by /workspace/skills/installer/plan
    plan_id: Optional[str] = None
    # Optional approval gate (similar to packages)
    require_approval: bool = False
    approval_request_id: Optional[str] = None
    details: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SkillInstallerUpdateRequest(BaseModel):
    scope: str = "workspace"
    ref: Optional[str] = None  # if omitted, keep existing manifest ref (git only)
    metadata: Optional[Dict[str, Any]] = None



# ---------------------------------------------------------------------
# PR-02: Run Contract v2 (unified run_id + status machine)


class RunStatus(str, Enum):
    accepted = "accepted"
    running = "running"
    waiting_approval = "waiting_approval"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"
    timeout = "timeout"


class RunError(BaseModel):
    code: str
    message: str
    detail: Optional[Dict[str, Any]] = None


class RunSummary(BaseModel):
    ok: bool
    run_id: str
    trace_id: Optional[str] = None
    status: RunStatus
    output: Optional[Any] = None
    error: Optional[RunError] = None
    # Keep extra fields for forward/backward compat
    metadata: Optional[Dict[str, Any]] = None


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


class PackageUninstallRequest(BaseModel):
    package_name: Optional[str] = None  # allow body override; path param is authoritative
    keep_modified: bool = True
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


class OnboardingSecretsMigrateRequest(BaseModel):
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingStrongGateRequest(BaseModel):
    tenant_id: str = "default"
    enabled: bool = True
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingExecBackendRequest(BaseModel):
    backend: str = "local"  # local|docker
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingTrustedSkillKeysRequest(BaseModel):
    # List of {key_id, public_key}; if key_id omitted, server will derive a deterministic id.
    keys: List[Dict[str, Any]] = Field(default_factory=list)
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingContextConfigRequest(BaseModel):
    """
    Runtime context behavior toggles (persisted as global_setting: key='context').
    NOTE: This is diagnostics/onboarding oriented; service restart may still require
    environment configuration depending on deployment.
    """

    enable_session_search: Optional[bool] = None
    context_token_limit: Optional[int] = None
    context_char_limit: Optional[int] = None
    context_max_messages: Optional[int] = None
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class DiagnosticsPromptAssembleRequest(BaseModel):
    """
    Diagnostics-only endpoint helper to introspect prompt/context assembly.
    """

    session_id: Optional[str] = None
    user_id: str = "system"
    repo_root: Optional[str] = None
    messages: Optional[list] = None  # list[{"role": "...", "content": "..."}]
    enable_project_context: bool = True
    enable_session_search: Optional[bool] = None  # None=use env


class PromptTemplateUpsertRequest(BaseModel):
    template_id: str
    name: str
    template: str
    metadata: Optional[Dict[str, Any]] = None
    increment_version: bool = True
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class PromptTemplateRollbackRequest(BaseModel):
    template_id: str
    version: str
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class RepoChangesetPreviewRequest(BaseModel):
    repo_root: str
    include_patch: bool = False  # default: do NOT return full diff
    note: Optional[str] = None
    run_tests: bool = False
    # Governance: when changeset is high-risk or non-local backend, require approval.
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    user_id: Optional[str] = None


class RepoTestsRunRequest(BaseModel):
    repo_root: str
    note: Optional[str] = None


class RepoStagedPreviewRequest(BaseModel):
    repo_root: str
    include_patch: bool = False


class RepoGitBranchRequest(BaseModel):
    repo_root: str
    branch: str
    base: Optional[str] = None  # base ref, default: current HEAD
    checkout: bool = True
    # Governance
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    user_id: Optional[str] = None
    change_id: Optional[str] = None  # optional linkage to an existing change
    details: Optional[str] = None


class RepoGitCommitRequest(BaseModel):
    repo_root: str
    message: str
    # Governance
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    user_id: Optional[str] = None
    change_id: Optional[str] = None  # optional linkage to an existing change
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
