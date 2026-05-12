"""
Builder pipeline schemas — four-role requirement-driven development.

v2: Added HITL approval phases, BugFixRecord, stagnation detection.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────

class BuilderSessionPhase(str, Enum):
    # ── Framework-level phases (application-agnostic) ──
    dialogue = "dialogue"
    executing = "executing"
    paused = "paused"
    done = "done"
    failed = "failed"
    # ── Backward-compat business phase names (exception to §5.29) ──
    # These exist because the management frontend, AGENT.md files, and
    # platform session service still reference them by value. New code
    # should use the framework-level 'paused' state + stage.hitl_phase.
    # Removal plan: after AGENT.md migration and frontend decoupling.
    awaiting_architecture_approval = "awaiting_architecture_approval"
    awaiting_test_plan_approval = "awaiting_test_plan_approval"
    awaiting_test_report_review = "awaiting_test_report_review"


class AgentDecision(str, Enum):
    PROCEED = "PROCEED"
    BLOCKED = "BLOCKED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class AgentConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IssueSeverity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class TestRecommendation(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class UserStoryPriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


# ── Structured artifacts ───────────────────────────────────────────

class UserStory(BaseModel):
    id: str
    description: str
    acceptance_criteria: List[str] = Field(default_factory=list)
    priority: UserStoryPriority = UserStoryPriority.P1


class PRDArtifact(BaseModel):
    title: str
    overview: str = ""
    user_stories: List[UserStory] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    scope: str = ""


class ComponentSpec(BaseModel):
    name: str
    responsibility: str
    dependencies: List[str] = Field(default_factory=list)


class ArchitectureArtifact(BaseModel):
    components: List[ComponentSpec] = Field(default_factory=list)
    data_model: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    api_contracts: List[Dict[str, Any]] = Field(default_factory=list)
    tech_stack: Dict[str, Any] = Field(default_factory=dict)


class FileArtifact(BaseModel):
    path: str
    content: str


class BugFixRecord(BaseModel):
    bug_id: str
    test_case_id: str
    description: str
    fix_date: str = ""
    fix_method: str = ""
    file_name: str = ""
    iteration: int = 0
    qa_retry: int = 0
    fixed: bool = False


class CodeArtifact(BaseModel):
    files: List[FileArtifact] = Field(default_factory=list)
    skills_created: List[str] = Field(default_factory=list)
    agents_created: List[str] = Field(default_factory=list)
    tools_created: List[str] = Field(default_factory=list)
    bug_fixes: List[BugFixRecord] = Field(default_factory=list)


class TestCase(BaseModel):
    id: str
    description: str
    acceptance_criteria_id: str = ""
    script: str = ""
    expected: str = ""


class TestCaseResult(BaseModel):
    test_case_id: str
    passed: bool
    actual: str = ""
    error: str = ""


class TestReport(BaseModel):
    test_cases: List[TestCase] = Field(default_factory=list)
    results: List[TestCaseResult] = Field(default_factory=list)
    pass_rate: float = 0.0
    issues: List[str] = Field(default_factory=list)
    recommendation: TestRecommendation = TestRecommendation.REJECTED
    scores: Dict[str, float] = Field(default_factory=dict)
    bug_fixes: List[BugFixRecord] = Field(default_factory=list)


# ── Issue / escalation ─────────────────────────────────────────────

class Issue(BaseModel):
    severity: IssueSeverity = IssueSeverity.P1
    description: str
    target_agent: str = ""
    suggestion: str = ""


class AgentOutput(BaseModel):
    artifact: Optional[Any] = None
    confidence: AgentConfidence = AgentConfidence.MEDIUM
    issues: List[Issue] = Field(default_factory=list)
    decision: AgentDecision = AgentDecision.PROCEED


# ── Pipeline state ─────────────────────────────────────────────────

class BuilderSessionStateResponse(BaseModel):
    session_id: str
    phase: BuilderSessionPhase
    requirement: str = ""
    prd: Optional[PRDArtifact] = None
    architecture: Optional[ArchitectureArtifact] = None
    code: Optional[CodeArtifact] = None
    test_report: Optional[TestReport] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    iteration: int = 0
    tokens_used: int = 0
    tokens_budget: int = 0
    stagnation_count: int = 0
    error: str = ""


class BuilderChatResponse(BaseModel):
    reply: str
    session_state: BuilderSessionStateResponse
    prd_ready: bool = False
    trace_id: Optional[str] = None


# ── Team Assembly schemas ─────────────────────────────────────────

class PipelineStageConfig(BaseModel):
    model_config = {"extra": "ignore"}
    id: str
    agent_id: str
    agent_name: str = ""
    description: str = ""
    category: str = ""
    tags: List[str] = Field(default_factory=list)
    phase: str = ""
    order: int = 0
    model: str = ""
    hitl: bool = False
    agent_type: str = "react"  # react, conversational, rag, plan_execute, reflection, tool_using, multi_agent
    hitl_phase: str = ""
    hitl_after_execute: bool = False
    hitl_after_phase: str = ""
    retry_target_id: str = ""
    generate_test_plan: bool = False
    test_result_key: str = "test_report"
    uses_code_skill: bool = False
    code_target: str = os.getenv("AIPLAT_DEFAULT_CODE_TARGET", "")
    language: str = ""
    prompt_extra: str = ""
    phase_description: str = ""
    input_artifacts: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    output_artifact: str = ""
    required_skills: List[str] = Field(default_factory=list)
    failure_strategy: str = "fail_pipeline"
    fallback_result_key: str = ""
    retry_llm_on_rate_limit: bool = True
    max_consecutive_llm_failures: int = 3
    stage_timeout_seconds: int = 600
    sandbox: bool = False
    scoring_dimensions: List[Dict[str, Any]] = Field(default_factory=list)
    coverage_trace_fields: Dict[str, str] = Field(default_factory=lambda: {"components_key": "components", "api_contracts_key": "api_contracts", "data_model_key": "data_model", "files_key": "files", "test_cases_key": "test_cases"})


class PipelineConfig(BaseModel):
    stages: List[PipelineStageConfig] = Field(default_factory=list)
    max_iterations: int = 3
    max_tokens_per_run: int = 100000
    max_stagnation: int = 3
    max_retry_attempts: int = 3
    max_steps_per_stage: int = 10
    deploy_strategy: str = "local"


class TeamConfig(BaseModel):
    team_id: str = ""
    name: str = ""
    description: str = ""
    stages: List[PipelineStageConfig] = Field(default_factory=list)
    max_iterations: int = 3
    max_tokens_per_run: int = 100000
    max_stagnation: int = 3
    max_retry_attempts: int = 3
    created_at: str = ""
    updated_at: str = ""


class TeamAssembleRequest(BaseModel):
    model_config = {"extra": "ignore"}
    name: str = ""
    description: str = ""
    stages: List[PipelineStageConfig] = Field(default_factory=list)
    max_tokens_per_run: int = 100000


class TeamRunResponse(BaseModel):
    run_id: str
    team_id: str
    phase: BuilderSessionPhase
    pipeline_state: Optional[Dict[str, Any]] = None


class AgentCatalogItem(BaseModel):
    agent_id: str
    display_name: str
    description: str
    agent_type: str
    category: str = ""
    tags: List[str] = Field(default_factory=list)
    phase: str = ""
    protected: bool = False
    scope: str = "engine"


class AgentCatalogResponse(BaseModel):
    categories: Dict[str, List[AgentCatalogItem]] = Field(default_factory=dict)
    total: int = 0


# ── Project Workbench schemas ──────────────────────────────────────

class ProjectRun(BaseModel):
    run_id: str = ""
    project_id: str = ""
    phase: str = ""
    pass_rate: float = 0.0
    tokens_used: int = 0
    iteration: int = 0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


class Project(BaseModel):
    project_id: str = ""
    name: str = ""
    description: str = ""
    team_id: str = ""
    team_name: str = ""
    team_stages: List[PipelineStageConfig] = Field(default_factory=list)
    runs: List[ProjectRun] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class ProjectCreateRequest(BaseModel):
    name: str = ""
    description: str = ""
    team_id: str = ""


class ProjectListResponse(BaseModel):
    projects: List[Project] = Field(default_factory=list)
    total: int = 0
