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


class ISCMetric(BaseModel):
    """Ideal State Criterion — a single verifiable completion standard."""
    id: str  # ISC-01, ISC-02, ...
    name: str
    criteria: str  # How to verify this ISC is met
    verification_method: str = "manual"  # manual | test | llm_eval | code_review


class ISAArtifact(BaseModel):
    """Ideal State Artifact — upgraded PRD with verifiable completion standards."""
    title: str
    target_state: str = ""  # What "done" looks like
    isc_list: List[ISCMetric] = Field(default_factory=list)  # Ideal State Criteria
    alignment_score: float = 0.0  # 0.0-1.0, set during QA evaluation
    current_state_summary: str = ""
    gap_analysis: str = ""


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
    # Generic artifacts dict keyed by stage.output_artifact (Phase 3 generalization)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    # @backward-compat: kept for existing frontend teams using standard pipeline.
    # @deprecated: use artifacts dict keyed by stage.output_artifact instead.
    # Migration plan: after frontend decouples from typed fields (ETA 2026-Q3),
    # remove these four fields and keep only the generic 'artifacts' dict.
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


class BuilderChatRequest(BaseModel):
    message: str


class BuilderSessionCreateRequest(BaseModel):
    requirement: str = ""


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
    test_result_key: str = "test_report"  # DEFAULT_TEST_RESULT_KEY — changed via AGENT.md frontmatter
    uses_file_output: bool = False
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
    sandbox_mode: str = "subprocess"
    sandbox_cpu_limit_seconds: int = 300
    sandbox_memory_limit_mb: int = 1024
    sandbox_max_processes: int = 100
    # Phase 10 — declarative execution mode (replaces if/elif chains in engine)
    execution_mode: str = "code_first"   # "code_first" | "tdd" | "plan_only"
    review_gate: str = "quick"           # "none" | "quick" | "llm" | "hitl" — default quick for safety
    tdd_enforce: bool = False
    context_isolation: str = "shared"   # "shared" | "isolated"
    eval_model: str = ""  # dedicated evaluator model (empty = fallback to stage.model or AIPLAT_EVAL_MODEL)
    routing_rules: List[dict] = Field(default_factory=list)  # declarative conditional routing
    deviation_tolerance: float = 0.0  # [0.0, 10.0] Accept output when overall score >= this (0=disabled)
    failure_mode_constraints: List[Dict[str, Any]] = Field(default_factory=list)
    # [{failure_type, constraint_action, max_escalation}] — targeted recovery per failure type
    # Empty list = use system DEFAULT_FAILURE_MODE_CONSTRAINTS
    enable_query_rewrite: bool = True  # rewrite ambiguous follow-up queries before retrieval
    scoring_dimensions: List[Dict[str, Any]] = Field(default_factory=list)
    coverage_trace_fields: Dict[str, str] = Field(default_factory=lambda: {"components_key": "components", "api_contracts_key": "api_contracts", "data_model_key": "data_model", "files_key": "files", "test_cases_key": "test_cases"})
    # Debate pattern: stage uses adversarial multi-agent debate (TradingAgents-inspired)
    debate_participants: List[Dict[str, Any]] = Field(default_factory=list)
    debate_max_rounds: int = 3
    debate_manager_agent: str = ""
    # Node-type-specific config from workflow canvas (llm/code/http/condition)
    node_config: Dict[str, Any] = Field(default_factory=dict)
    node_type: str = "agent"  # "agent" | "llm" | "code" | "http" | "condition" | "knowledge" | "tool" | "list" | "assigner" | "template" | "loop" | "aggregator"
    # Render config: inject upstream outputs as Markdown into stage prompt
    render_upstream: bool = False
    render_schema_fields: List[Dict[str, Any]] = Field(default_factory=list)
    # Knowledge base binding: collections the agent's wiki search is scoped to
    knowledge_bases: List[str] = Field(default_factory=list)


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
    stages: List[Dict[str, Any]] = Field(default_factory=list)  # pre-built workflow stages


class ProjectListResponse(BaseModel):
    projects: List[Project] = Field(default_factory=list)
    total: int = 0


# ── Health Report (Phase R2: quality scoring across dimensions) ──

class HealthDimension(BaseModel):
    """Single quality dimension score."""
    name: str
    display_name: str = ""
    score: float = 0.0
    max_score: float = 10.0
    weight: float = 1.0
    pass_threshold: float = 7.0
    issues_count: int = 0


class StageHealthReport(BaseModel):
    """Per-stage health report."""
    stage_id: str
    agent_id: str = ""
    dimensions: List[HealthDimension] = Field(default_factory=list)
    overall_score: float = 0.0
    verdict: str = "pending"  # passed | partial | failed | pending


class ProjectHealthReport(BaseModel):
    """Aggregated health report for a project."""
    project_id: str
    overall_score: float = 0.0  # 0-100
    dimensions: List[HealthDimension] = Field(default_factory=list)
    stages: List[StageHealthReport] = Field(default_factory=list)
    trend: List[Dict[str, Any]] = Field(default_factory=list)  # [{run_id, score, timestamp}]
    updated_at: str = ""
