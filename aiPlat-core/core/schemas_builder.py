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
    agent_type: str = "react"  # See ~/.aiplat/registry/agent_types.yaml for valid values (single source of truth)
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
    skill_name: str = ""                 # e.g., "architecture_design", "code_generation"
    skill_model_purpose: str = ""        # e.g., "reasoning", "code_gen" — passed to best_model_for_purpose
    review_gate: str = "quick"           # "none" | "quick" | "llm" | "hitl" — default quick for safety
    tdd_enforce: bool = False
    context_isolation: str = "shared"   # "shared" | "isolated"
    context_profile: str = "code"        # "minimal" | "code" | "debug" | "deep"
    # Phase 11 — config-driven post-execution (replaces hardcoded business logic in engine)
    chain_skill_after: str = ""          # Auto-execute another skill after this stage completes
    deploy_files_to_disk: bool = False   # Parse ## FILE: blocks from output, write to project dir
    deploy_files_target_dir: str = ""    # Override target. Empty = ~/.aiplat/apps/{pid}/current
    test_execution_mode: str = ""        # "pytest" | "agent_conversation" | "" — which test runner
    # Phase 12 — execution backend selection (replaces SOP detection / agent_type switching)
    execution_backend: str = "llm"       # "llm"=sys_llm_generate | "agent"=StageRunner.run()→ReActLoop
    # Anthropic 5 patterns: chain | router | parallel | orchestrator | evaluator_optimizer
    pipeline_mode: str = "chain"          # "chain" | "router" | "parallel" | "orchestrator" | "evaluator_optimizer" | "agent"
    routing_mode: str = "static"           # "static" | "llm" | "debate" | "swarm" | "roundtable" | "moa" — routing strategy
    eval_model: str = ""  # dedicated evaluator model (empty = fallback to stage.model or AIPLAT_EVAL_MODEL)
    routing_rules: List[dict] = Field(default_factory=list)  # declarative conditional routing  # 4step-verified
    deviation_tolerance: float = 0.0  # [0.0, 10.0] Accept output when overall score >= this (0=disabled)
    failure_mode_constraints: List[Dict[str, Any]] = Field(default_factory=list)
    # [{failure_type, constraint_action, max_escalation}] — targeted recovery per failure type
    # Empty list = use system DEFAULT_FAILURE_MODE_CONSTRAINTS
    enable_query_rewrite: bool = True  # rewrite ambiguous follow-up queries before retrieval
    scoring_dimensions: List[Dict[str, Any]] = Field(default_factory=lambda: [
        {"name": "completeness", "weight": 0.4},
        {"name": "accuracy", "weight": 0.3},
        {"name": "efficiency", "weight": 0.3},
    ])
    # Fine-grained per-stage reward weights (UnityMAS-O inspired)
    scoring_weights: Dict[str, float] = Field(default_factory=lambda: {
        "output_quality": 0.40, "token_efficiency": 0.15,
        "latency_score": 0.10, "downstream_impact": 0.25,
        "review_pass": 0.10,
    })
    # Declarative cross-entity property propagation (OntoGraph-inspired)
    propagation_rules: List[Dict[str, Any]] = Field(default_factory=list)
    # [{source_entity, source_prop, target_entity, target_prop, aggregation}]
    # Parallel state merge strategies for reducer (prevents overwrite in parallel stages)
    merge_strategies: Dict[str, str] = Field(default_factory=lambda: {})  # {"messages": "append", "trace": "append", ...}
    coverage_trace_fields: Dict[str, str] = Field(default_factory=lambda: {"components_key": "components", "api_contracts_key": "api_contracts", "data_model_key": "data_model", "files_key": "files", "test_cases_key": "test_cases"})
    # Debate pattern: stage uses adversarial multi-agent debate (TradingAgents-inspired)
    debate_participants: List[Dict[str, Any]] = Field(default_factory=list)
    debate_max_rounds: int = 3
    debate_manager_agent: str = ""
    # MoA (Mixture of Agents) routing: parallel reference engines + aggregator synthesis
    moa_preset: str = "general"
    moa_reference_count: int = 3
    # Node-type-specific config from workflow canvas (llm/code/http/condition)
    node_config: Dict[str, Any] = Field(default_factory=dict)
    node_type: str = "agent"  # "agent" | "llm" | "code" | "http" | "condition" | "knowledge" | "tool" | "list" | "assigner" | "template" | "loop" | "aggregator"
    # Render config: inject upstream outputs as Markdown into stage prompt
    render_upstream: bool = False
    render_schema_fields: List[Dict[str, Any]] = Field(default_factory=list)
    # Knowledge base binding: collections the agent's wiki search is scoped to
    knowledge_bases: List[str] = Field(default_factory=list)
    # Ontology integration: stage output → ontology entity auto-registration
    ontology_class: str = ""
    ontology_relations: List[Dict[str, str]] = Field(default_factory=list)
    ontology_action_verb: str = ""
    ontology_preconditions: List[str] = Field(default_factory=list)
    ontology_target_state: str = "proposed"
    # Verification: expected outcomes for stage output validation
    expected_outcomes: List[Dict[str, Any]] = Field(default_factory=list)
    # External rubric file (YAML/JSON) for independent assessment
    rubric_path: str = ""
    # Scene model: scene ID for context injection and template tracking
    scene_id: str = ""
    # Planner-Generator-Evaluator separation: stage ID for structured planning
    planning_stage_id: str = ""
    # ── v4.0: Declarative quality gates & routing for pipeline agents ──
    quality_gate: Dict[str, Any] = Field(default_factory=lambda: {"min_output_length": 100})
    """CRAG-style quality gate: {condition, fallback, final_fallback}"""
    routing_rules: Dict[str, Any] = Field(default_factory=dict)  # 4step-verified: wired via pipeline_compiler.py + engine.py:1900
    """Domain routing rules: {tiers, fallback_domain}"""
    retry_policy: Dict[str, Any] = Field(default_factory=lambda: {"max_retries": 2, "backoff": "exponential"})
    """Self-heal retry: {on, action, max_retries}"""
    # ── v4.1: Cross-stage rollback (delegation + adversarial pattern) ──
    rollback_on_reject: bool = False
    """When evaluation REJECTED, rollback to upstream stage instead of same-stage retry."""
    rollback_target_id: str = ""
    """Target stage ID to rollback to when rejected (empty = use depends_on for upstream)."""


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

# ═══════════════════════════════════════════════════════════════
# Spec lifecycle response models (migrated from Dict[str,Any] 2026-07-13)
# ═══════════════════════════════════════════════════════════════

class SpecVersionSummary(BaseModel):
    version: Any = ""
    status: str = ""
    trigger: str = ""
    trigger_detail: str = ""
    created_at: str = ""

class SpecHistoryResponse(BaseModel):
    spec_id: str
    versions: List[SpecVersionSummary] = Field(default_factory=list)
    total: int = 0
    error: Optional[str] = None

class SpecRevisionResponse(BaseModel):
    spec_id: str
    version: Any = ""
    status: str = ""
    affected_stages: List[str] = Field(default_factory=list)
    trigger: str = ""
    trigger_detail: str = ""
    re_execute: bool = False
    run_id: Optional[str] = None
    re_execution_triggered: Optional[bool] = None
    re_execution_error: Optional[str] = None

class SpecCreatedResponse(BaseModel):
    spec_id: str
    version: Any = ""
    status: str = ""
    source: Optional[str] = None
    source_version: Optional[str] = None

class SpecMarkStableResponse(BaseModel):
    spec_id: str
    status: str  # "stable" or "unchanged"
    version: Any = ""
    reason: Optional[str] = None

class SpecRadarSuggestion(BaseModel):
    type: str = ""
    severity: str = ""
    detail: str = ""
    suggested_action: str = ""
    evidence_count: int = 0

class SpecRadarResponse(BaseModel):
    spec_id: str
    suggestions: List[SpecRadarSuggestion] = Field(default_factory=list)
    total: int = 0
    error: Optional[str] = None

class SpecTraceResponse(BaseModel):
    spec_id: str
    version: Any = ""
    status: str = ""
    total_steps: int = 0
    agent_call_order: List[str] = Field(default_factory=list)
    hesitation_count: int = 0
    repeat_count: int = 0
    decision_chain: str = ""
    anomaly_report: str = ""
    spec_suggestions: List[str] = Field(default_factory=list)
    anomalies: List[str] = Field(default_factory=list)
    raw_steps: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None

class VersionInfo(BaseModel):
    version: Any = ""
    status: str = ""
    content: Dict[str, Any] = Field(default_factory=dict)

class FieldChange(BaseModel):
    field: str
    before: Any = None
    after: Any = None

class SpecDiffResponse(BaseModel):
    spec_id: str
    source: VersionInfo = Field(default_factory=VersionInfo)
    target: VersionInfo = Field(default_factory=VersionInfo)
    changes: List[FieldChange] = Field(default_factory=list)
    total_changes: int = 0

class SpecListItem(BaseModel):
    spec_id: str
    version: Any = ""
    status: str = ""
    industry: str = ""
    created_at: str = ""

class SpecsListResponse(BaseModel):
    specs: List[SpecListItem] = Field(default_factory=list)
    total: int = 0
    error: Optional[str] = None

class TaskStatusResponse(BaseModel):
    run_id: str
    status: str = ""
    spec_id: str = ""
    stages: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None

class PromotionResponse(BaseModel):
    spec_id: str
    scope: str = ""
    promotion_status: str = ""
    reviewer: Optional[str] = None
