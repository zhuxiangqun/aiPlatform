"""
Builder pipeline schemas — four-role requirement-driven development.

v2: Added HITL approval phases, BugFixRecord, stagnation detection.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


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

# Declarative execution mix (W2/B1). Tool/Memory/RAG stay cross-cutting; these
# only set backend + loop shape. Unknown profile is ignored (compat).
ARCHITECTURE_PROFILES: Dict[str, Dict[str, str]] = {
    "oneshot": {"execution_backend": "llm", "agent_type": "react"},
    "react_tools": {"execution_backend": "agent", "agent_type": "react"},
    "plan_execute": {"execution_backend": "agent", "agent_type": "plan"},
    "reflect_loop": {"execution_backend": "agent", "agent_type": "reflection"},
}

# Non-file stages of these types use core_chat. File-output stages stay on
# StageRunner/ReAct even when architecture_profile is plan_execute.
CONVERSATIONAL_AGENT_TYPES = frozenset({
    "conversational",
    "rag",
    "plan",
    "plan_execute",
    "reflection",
    "review",
    "materials_chat",
})


def apply_architecture_profile(stage: "PipelineStageConfig") -> "PipelineStageConfig":
    """If architecture_profile is set, it wins over execution_backend/agent_type."""
    raw = str(getattr(stage, "architecture_profile", "") or "").strip().lower()
    spec = ARCHITECTURE_PROFILES.get(raw)
    if spec:
        stage.execution_backend = spec["execution_backend"]
        stage.agent_type = spec["agent_type"]
    pol = str(getattr(stage, "upgrade_policy", "") or "").strip().lower()
    if not pol:
        stage.upgrade_policy = "signals"
    elif pol in ("none", "disabled", "false", "0"):
        stage.upgrade_policy = "off"
    elif pol not in ("off", "signals", "aggressive"):
        stage.upgrade_policy = "signals"
    return apply_coding_stage_defaults(stage)


# Persisted on pipeline_stages.config_json so resume keeps coding closed-loop gates.
STAGE_CONFIG_PERSIST_KEYS = (
    "uses_file_output",
    "tdd_enforce",
    "refactor_sop",
    "done_verify",
    "review_gate",
    "sandbox",
    "sandbox_mode",
    "required_skills",
    "deploy_files_to_disk",
    "inject_imported_context",
    "quality_gate",
    "expected_outcomes",
    "architecture_profile",
    "architecture_mode",
    "execution_backend",
    "execution_mode",
    "skill_model_purpose",
    "code_target",
    "agent_type",
    "tools",
    "prompt_extra",
    "stage_timeout_seconds",
    "output_schema",
    "meta_tool",
)


def extract_stage_persist_config(raw: Any) -> Dict[str, Any]:
    """Compact stage overlay for SQLite resume (coding closed-loop + schedule)."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key in STAGE_CONFIG_PERSIST_KEYS:
        if key not in raw:
            continue
        val = raw[key]
        if val is None or val == "" or val == [] or val == {}:
            continue
        out[key] = val
    return out


def apply_template_stage_overlay(
    dest: Any, src: Any, *, only_missing: bool = False
) -> Any:
    """Copy template YAML fields (incl. refactor_sop / done_verify) onto a stage.

    ``dest`` may be a ``PipelineStageConfig`` or a mutable dict. Used by factory
    recommend_team when merging plan_stages with team template rows.
    When ``only_missing`` is True, do not overwrite non-empty destination values
    (bool ``False`` counts as missing so template ``True`` can fill).
    """
    if not isinstance(src, dict):
        return dest
    extra = ("completeness_check", "hitl", "hitl_phase", "input_artifacts", "skill_name", "output_artifact")
    keys = tuple(dict.fromkeys((*STAGE_CONFIG_PERSIST_KEYS, *extra)))

    def _empty(val: Any) -> bool:
        return val in (None, "", [], {})

    def _skip_existing(cur: Any, incoming: Any) -> bool:
        if not only_missing:
            return False
        if isinstance(incoming, bool):
            return cur is True  # keep explicit on; allow False→True
        return not _empty(cur)

    if isinstance(dest, dict):
        for key in keys:
            if key not in src:
                continue
            val = src[key]
            if _empty(val):
                continue
            if _skip_existing(dest.get(key), val):
                continue
            dest[key] = val
        return dest
    for key in keys:
        if key not in src or not hasattr(dest, key):
            continue
        val = src[key]
        if _empty(val):
            continue
        try:
            cur = getattr(dest, key)
        except Exception:
            cur = None
        if _skip_existing(cur, val):
            continue
        try:
            setattr(dest, key, val)
        except Exception:
            continue
    # Re-expand coding closed-loop after late refactor_sop / done_verify assignment.
    try:
        apply_coding_stage_defaults(dest)
    except Exception:
        import logging

        logging.getLogger(__name__).debug(
            "apply_coding_stage_defaults after overlay skipped", exc_info=True
        )
    return dest


def backfill_stage_from_team_templates(stage: "PipelineStageConfig") -> "PipelineStageConfig":
    """When resume lacks config_json, fill coding closed-loop from team YAML by agent_id."""
    aid = str(getattr(stage, "agent_id", "") or "").strip()
    if not aid:
        return stage
    try:
        from core.harness.execution.team_planner import list_team_templates
    except Exception:
        return stage
    try:
        for tmpl in list_team_templates():
            for ts in getattr(tmpl, "stages", None) or []:
                if isinstance(ts, dict) and str(ts.get("agent_id") or "") == aid:
                    # only_missing: do not overwrite fields already set on resume
                    # (first team YAML match must not clobber explicit config).
                    apply_template_stage_overlay(stage, ts, only_missing=True)
                    return stage
    except Exception:
        import logging

        logging.getLogger(__name__).debug(
            "backfill_stage_from_team_templates skipped", exc_info=True
        )
    return stage


def pipeline_stage_from_store_row(sr: Any) -> "PipelineStageConfig":
    """Rebuild ``PipelineStageConfig`` from a pipeline_stages row (+ config_json)."""
    row = sr if isinstance(sr, dict) else {}
    input_arts = row.get("input_artifacts", "")
    if isinstance(input_arts, list):
        inputs = [str(a).strip() for a in input_arts if str(a).strip()]
    else:
        inputs = [a.strip() for a in str(input_arts or "").split(",") if a.strip()]
    kwargs: Dict[str, Any] = {
        "id": str(row.get("stage_id") or row.get("id") or "stage"),
        "agent_id": str(row.get("agent_id") or ""),
        "agent_name": str(row.get("agent_name") or ""),
        "skill_name": str(row.get("skill_name") or ""),
        "output_artifact": str(
            row.get("output_artifact") or row.get("artifact_key") or ""
        ),
        "hitl": bool(row.get("hitl", False)),
        "hitl_phase": str(row.get("hitl_phase") or ""),
        "input_artifacts": inputs,
    }
    overlay: Dict[str, Any] = {}
    raw_cfg = row.get("config_json") or row.get("_stage_config") or ""
    if isinstance(raw_cfg, dict):
        overlay = dict(raw_cfg)
    elif isinstance(raw_cfg, str) and raw_cfg.strip():
        try:
            import json as _json

            parsed = _json.loads(raw_cfg)
            if isinstance(parsed, dict):
                overlay = parsed
        except Exception:
            overlay = {}
    if not overlay:
        prog = row.get("progress_json") or row.get("progress") or ""
        if isinstance(prog, dict):
            nested = prog.get("_stage_config")
            if isinstance(nested, dict):
                overlay = dict(nested)
        elif isinstance(prog, str) and prog.strip():
            try:
                import json as _json

                parsed = _json.loads(prog)
                if isinstance(parsed, dict) and isinstance(parsed.get("_stage_config"), dict):
                    overlay = dict(parsed["_stage_config"])
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "progress _stage_config json parse skipped", exc_info=True
                )
    fields = PipelineStageConfig.model_fields
    for key, val in overlay.items():
        if key in fields and key not in ("id",):
            kwargs[key] = val
    stage = PipelineStageConfig(**kwargs)
    # Legacy rows (pre-config_json): restore coding closed-loop from team seeds.
    if not overlay:
        backfill_stage_from_team_templates(stage)
    return stage


def stage_uses_react_loop(stage: Any, agent_type: str = "") -> bool:
    """File-output stages always use StageRunner/ReAct.

    ``plan`` / ``plan_execute`` only take the chat shortcut when the stage
    does not write files. Pipeline stages remain the schedule layer.
    """
    if bool(getattr(stage, "uses_file_output", False)):
        return True
    at = str(agent_type or getattr(stage, "agent_type", "") or "")
    return at not in CONVERSATIONAL_AGENT_TYPES


def file_stage_control_stack(stage: Any) -> Dict[str, str]:
    """Schedule / execute / external-quality stack actually used for a stage.

    Heavy coding is ready when execute is ReAct and quality is an external
    completion standard. LLM self-critique is not this quality layer.
    """
    file_out = bool(getattr(stage, "uses_file_output", False))
    profile = str(getattr(stage, "architecture_profile", "") or "").strip().lower()
    dv = getattr(stage, "done_verify", None)
    dv = dv if isinstance(dv, dict) else {}
    execute = "react" if stage_uses_react_loop(stage) else "chat"
    if not file_out:
        quality = "off"
    elif dv.get("require_completion_standard") and _file_delivery_has_standard(stage, dv):
        quality = "external"
    else:
        quality = "missing"
    schedule = "pipeline+plan_execute" if profile == "plan_execute" else "pipeline"
    return {"schedule": schedule, "execute": execute, "quality": quality}


def control_fuses_for_stage(
    stage: Any,
    *,
    max_steps: int = 0,
    quality_soft_veto_limit: int = 2,
) -> Dict[str, Any]:
    """Three-layer stack plus hard fuses (execute / quality / schedule).

    - execute: ReAct ``max_steps``
    - quality: soft done_verify vetoes before fail-open (hard standards never open)
    - schedule: ``upgrade_policy`` (off | signals | aggressive)
    """
    stack = file_stage_control_stack(stage)
    try:
        steps = int(max_steps or 0)
    except (TypeError, ValueError):
        steps = 0
    if steps <= 0:
        try:
            steps = max(1, int(os.getenv("AIPLAT_MAX_STEPS_PER_STAGE", "10") or 10))
        except (TypeError, ValueError):
            steps = 10
    try:
        soft = max(1, int(quality_soft_veto_limit or 2))
    except (TypeError, ValueError):
        soft = 2
    policy = str(getattr(stage, "upgrade_policy", "") or "signals").strip().lower() or "signals"
    return {
        "schedule": stack["schedule"],
        "execute": stack["execute"],
        "quality": stack["quality"],
        "fuses": {
            "execute_max_steps": steps,
            "quality_soft_veto_limit": soft,
            "schedule_upgrade_policy": policy,
        },
    }


def _file_delivery_has_standard(stage: "PipelineStageConfig", dv: Dict[str, Any]) -> bool:
    """True when a checkable completion standard is already configured."""
    if dv.get("expected_outcomes") or dv.get("require_keys") or dv.get("require_commands"):
        return True
    subs = dv.get("require_substrings")
    if isinstance(subs, list) and any(str(s).strip() for s in subs):
        return True
    for src in (dv.get("output_schema"), getattr(stage, "output_schema", None)):
        if isinstance(src, dict) and src:
            return True
    eo = getattr(stage, "expected_outcomes", None)
    return bool(isinstance(eo, list) and eo)


def apply_coding_stage_defaults(stage: "PipelineStageConfig") -> "PipelineStageConfig":
    """Config-driven coding closed loop for ``uses_file_output`` stages.

    Defaults (no agent_id branches): stage sandbox on (unless sandbox_mode=none),
    light done_verify + review_gate, bind autoreview so review_gate can enforce.
    When ``require_completion_standard`` is on and no standard is set, inject
    ``require_substrings: ["## FILE:"]`` (same marker as code_generation skill).
    Opt out: ``sandbox_mode: none``, ``review_gate: none``, or
    ``AIPLAT_CODING_STAGE_SANDBOX=false`` / ``AIPLAT_CODING_STAGE_AUTOREVIEW=false``.
    TDD before DONE: ``tdd_enforce: true`` or ``AIPLAT_CODING_STAGE_TDD=true``.
    Problem list before DONE: ``AIPLAT_CODING_STAGE_DIAGNOSIS=true`` (``[P0]``/``[P1]``/``[P2]``).
    Plan before code: ``AIPLAT_CODING_STAGE_PLAN=true`` (``## Refactor Plan`` / ``## 重构计划``).
    Dependency zones: ``AIPLAT_CODING_STAGE_DEPS=true`` (安全区 + 保护区).
    Rollback evidence: ``AIPLAT_CODING_STAGE_ROLLBACK=true`` (file checkpoint / git tag).
    Rollback command: ``AIPLAT_CODING_STAGE_ROLLBACK_CMD=true`` (git checkout/reset or FEATURE_*=false).
    Feature flag / canary: ``AIPLAT_CODING_STAGE_FLAG=true``.
    Hard review (Step 5): ``AIPLAT_CODING_STAGE_REQUIRE_REVIEW=true`` / SOP
    ``require_review`` — binds ``autoreview``, forces ``review_gate=quick``,
    and upgrades ``execution_backend=llm`` → ``agent`` (or ``oneshot`` →
    ``react_tools``) so ReAct can dispatch follow-up (oneshot cannot).
    ``AIPLAT_CODING_STAGE_KEEP_LLM`` is ignored under hard ``require_review``
    (schema hard-block: oneshot cannot satisfy review receipts).
    Full refactor SOP (1–7 + review): stage ``refactor_sop: true`` or
    ``AIPLAT_CODING_STAGE_REFACTOR_SOP=true``.
    File checkpoints remain global (sys_file_write), already default-on.
    """
    if not bool(getattr(stage, "uses_file_output", False)):
        return stage

    def _env_on(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")

    mode = str(getattr(stage, "sandbox_mode", "") or "").strip().lower()
    sandbox_default = os.getenv("AIPLAT_CODING_STAGE_SANDBOX", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if mode != "none" and sandbox_default and not bool(getattr(stage, "sandbox", False)):
        stage.sandbox = True

    sop_default = bool(getattr(stage, "refactor_sop", False)) or _env_on(
        "AIPLAT_CODING_STAGE_REFACTOR_SOP"
    )
    tdd_default = sop_default or _env_on("AIPLAT_CODING_STAGE_TDD")
    if tdd_default and not bool(getattr(stage, "tdd_enforce", False)):
        stage.tdd_enforce = True
    diagnosis_default = sop_default or _env_on("AIPLAT_CODING_STAGE_DIAGNOSIS")
    plan_default = sop_default or _env_on("AIPLAT_CODING_STAGE_PLAN")
    deps_default = sop_default or _env_on("AIPLAT_CODING_STAGE_DEPS")
    rollback_default = sop_default or _env_on("AIPLAT_CODING_STAGE_ROLLBACK")
    rollback_cmd_default = sop_default or _env_on("AIPLAT_CODING_STAGE_ROLLBACK_CMD")
    flag_default = sop_default or _env_on("AIPLAT_CODING_STAGE_FLAG")
    review_default = sop_default or _env_on("AIPLAT_CODING_STAGE_REQUIRE_REVIEW")
    if sop_default:
        rg_now = str(getattr(stage, "review_gate", "") or "").strip().lower()
        if not rg_now or rg_now in ("off", "false", "0", "no"):
            stage.review_gate = "quick"

    dv = getattr(stage, "done_verify", None)
    if not isinstance(dv, dict) or not dv:
        rg = str(getattr(stage, "review_gate", "") or "quick").strip().lower() or "quick"
        stage.done_verify = {
            "enabled": True,
            "min_output_length": 20,
            "reject_trivial_done": True,
            "reject_action_envelope": True,
            "review_gate": rg if rg != "none" else "none",
            # P1: handlers in file-output stages must get pure unit tests.
            "require_testability": True,
            "testability_mode": "",  # empty → YAML/env resolve_mode (warn→block_after)
            # Delivery cannot seal DONE on length alone.
            "require_completion_standard": True,
            "require_tdd": bool(getattr(stage, "tdd_enforce", False)),
            "require_diagnosis": diagnosis_default,
            "require_refactor_plan": plan_default,
            "require_dependency_map": deps_default,
            "require_rollback_checkpoint": rollback_default,
            "require_rollback_command": rollback_cmd_default,
            "require_feature_flag": flag_default,
            "require_review": review_default,
        }
    elif isinstance(dv, dict):
        dv = dict(dv)
        if "require_testability" not in dv:
            dv["require_testability"] = True
        if "require_completion_standard" not in dv:
            dv["require_completion_standard"] = True
        if bool(getattr(stage, "tdd_enforce", False)):
            dv.setdefault("require_tdd", True)
        if diagnosis_default:
            dv.setdefault("require_diagnosis", True)
        if plan_default:
            dv.setdefault("require_refactor_plan", True)
        if deps_default:
            dv.setdefault("require_dependency_map", True)
        if rollback_default:
            dv.setdefault("require_rollback_checkpoint", True)
        if rollback_cmd_default:
            dv.setdefault("require_rollback_command", True)
        if flag_default:
            dv.setdefault("require_feature_flag", True)
        if review_default:
            dv.setdefault("require_review", True)
        stage.done_verify = dv

    # Default checkable standard for file delivery (config-driven; not agent_id).
    # Explicit empty require_substrings still blocks until another standard is set.
    dv = dict(getattr(stage, "done_verify", None) or {})
    if dv.get("require_completion_standard") and not _file_delivery_has_standard(stage, dv):
        if "require_substrings" not in dv:
            dv["require_substrings"] = ["## FILE:"]
            stage.done_verify = dv

    rg = str(getattr(stage, "review_gate", "") or "quick").strip().lower()
    autoreview_default = os.getenv("AIPLAT_CODING_STAGE_AUTOREVIEW", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    # Hard require_review (SOP Step 5) always binds autoreview — even when the
    # soft AIPLAT_CODING_STAGE_AUTOREVIEW switch is off or review_gate is none.
    dv_now = getattr(stage, "done_verify", None)
    hard_review = review_default or (
        isinstance(dv_now, dict) and bool(dv_now.get("require_review"))
    )
    need_ar = hard_review or (
        autoreview_default and rg not in ("", "none", "off", "false", "0")
    )
    if hard_review and rg in ("", "none", "off", "false", "0", "no"):
        stage.review_gate = "quick"
        rg = "quick"
        if isinstance(dv_now, dict):
            dv_fix = dict(dv_now)
            dv_fix["review_gate"] = "quick"
            stage.done_verify = dv_fix
    if need_ar:
        skills = list(getattr(stage, "required_skills", None) or [])
        if "autoreview" not in skills:
            skills.append("autoreview")
            stage.required_skills = skills
    # Hard review needs a tool loop — oneshot llm cannot produce autoreview receipts.
    # KEEP_LLM must not leave an unsatisfiable config (schema hard-block).
    if hard_review:
        if _env_on("AIPLAT_CODING_STAGE_KEEP_LLM"):
            import logging

            logging.getLogger(__name__).warning(
                "AIPLAT_CODING_STAGE_KEEP_LLM ignored: require_review needs "
                "react_tools (oneshot cannot dispatch autoreview)"
            )
        ap = str(getattr(stage, "architecture_profile", "") or "").strip().lower()
        eb = str(getattr(stage, "execution_backend", "") or "llm").strip().lower()
        # plan_execute / reflect_loop / react_tools already run agent loops.
        if ap not in ("plan_execute", "reflect_loop", "react_tools") and (
            ap in ("", "oneshot") or eb in ("", "llm")
        ):
            stage.architecture_profile = "react_tools"
            apply_architecture_profile(stage)
    return stage


def _truthy_flag(val: Any) -> bool:
    if val is True:
        return True
    if isinstance(val, (int, float)) and val == 1:
        return True
    return str(val or "").strip().lower() in ("1", "true", "yes", "on")


def _dict_declares_coding(d: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(d, dict):
        return False
    return _truthy_flag(d.get("uses_file_output")) or _truthy_flag(d.get("uses_code_skill"))


def _skill_declares_coding(skill: Any) -> bool:
    """True when skill config/frontmatter marks file-output / code skill (no name matching)."""
    if skill is None:
        return False
    config = getattr(skill, "_config", None)
    if config is None and callable(getattr(skill, "get_config", None)):
        try:
            config = skill.get_config()
        except Exception:
            config = None
    for obj in (skill, config):
        if obj is None:
            continue
        if bool(getattr(obj, "uses_file_output", False) or getattr(obj, "uses_code_skill", False)):
            return True
        meta = getattr(obj, "metadata", None)
        if _dict_declares_coding(meta if isinstance(meta, dict) else None):
            return True
    return False


def workspace_agent_needs_coding_defaults(
    *,
    agent_cfg: Optional[Dict[str, Any]] = None,
    agent_meta: Optional[Dict[str, Any]] = None,
    skills: Optional[List[Any]] = None,
) -> bool:
    """Config/skill-signal check — never agent_id string matching.

    Opt in: ``uses_file_output`` / ``uses_code_skill`` on agent or bound skills,
    ``coding_closed_loop: true``, or non-off ``coding_intensity``.
    Opt out: ``coding_closed_loop: false`` (wins over skill signals).
    Does **not** treat ``coding_policy_profile`` alone as opt-in (karpathy is
    often set without meaning a file-output coding agent).
    """
    cfg = agent_cfg if isinstance(agent_cfg, dict) else {}
    meta = agent_meta if isinstance(agent_meta, dict) else {}
    for d in (cfg, meta):
        raw = d.get("coding_closed_loop")
        if raw is None:
            continue
        s = str(raw).strip().lower()
        if s in ("0", "false", "off", "none", "no"):
            return False
        if _truthy_flag(raw):
            return True
    if _dict_declares_coding(cfg) or _dict_declares_coding(meta):
        return True
    for sk in skills or []:
        if _skill_declares_coding(sk):
            return True
    for d in (cfg, meta):
        inten = str(d.get("coding_intensity") or "").strip().lower()
        if inten and inten not in ("off", "none", "0", "false"):
            return True
    return False


def inject_workspace_coding_defaults(
    state: Dict[str, Any],
    *,
    agent_cfg: Optional[Dict[str, Any]] = None,
    agent_meta: Optional[Dict[str, Any]] = None,
    skills: Optional[List[Any]] = None,
) -> List[str]:
    """Upgrade Workspace Execute state to the same coding closed loop as factory stages.

    When agent/skills declare file-output coding: set ``_coding_policy_profile`` from
    intensity, merge ``apply_coding_stage_defaults`` into ``_done_verify``, and return
    extra skill ids to bind (e.g. ``autoreview`` for review_gate follow-up).

    Non-coding trial agents stay on profile ``off`` (slim CLAUDE inject). Opt out:
    ``coding_closed_loop: false`` on AGENT.md config/metadata.
    """
    if not isinstance(state, dict):
        return []
    if not workspace_agent_needs_coding_defaults(
        agent_cfg=agent_cfg, agent_meta=agent_meta, skills=skills
    ):
        return []

    cfg = agent_cfg if isinstance(agent_cfg, dict) else {}
    meta = agent_meta if isinstance(agent_meta, dict) else {}

    dv_seed = state.get("_done_verify") if isinstance(state.get("_done_verify"), dict) else None
    if dv_seed is None and isinstance(cfg.get("done_verify"), dict):
        dv_seed = cfg.get("done_verify")
    if dv_seed is None and isinstance(meta.get("done_verify"), dict):
        dv_seed = meta.get("done_verify")

    rg = str(cfg.get("review_gate") or meta.get("review_gate") or state.get("review_gate") or "quick")
    req = []
    for src in (
        cfg.get("required_skills"),
        meta.get("required_skills"),
        state.get("_bound_skill_ids"),
    ):
        if isinstance(src, list):
            for x in src:
                s = str(x).strip()
                if s and s not in req:
                    req.append(s)

    _qg = (
        cfg.get("quality_gate")
        if isinstance(cfg.get("quality_gate"), dict)
        else (meta.get("quality_gate") if isinstance(meta.get("quality_gate"), dict) else {})
    )
    _eo = cfg.get("expected_outcomes") if isinstance(cfg.get("expected_outcomes"), list) else None
    if _eo is None and isinstance(meta.get("expected_outcomes"), list):
        _eo = meta.get("expected_outcomes")
    _sm = str(cfg.get("sandbox_mode") or meta.get("sandbox_mode") or "").strip()
    _refactor_sop = _truthy_flag(cfg.get("refactor_sop")) or _truthy_flag(
        meta.get("refactor_sop")
    ) or _truthy_flag(state.get("refactor_sop"))
    _tdd = (
        _truthy_flag(cfg.get("tdd_enforce"))
        or _truthy_flag(meta.get("tdd_enforce"))
        or _truthy_flag(state.get("tdd_enforce"))
        or _refactor_sop
    )
    stage_kw: Dict[str, Any] = {
        "id": "workspace_agent",
        "agent_id": "",
        "uses_file_output": True,
        "done_verify": dict(dv_seed) if isinstance(dv_seed, dict) else {},
        "review_gate": rg,
        "required_skills": list(req),
        "sandbox": bool(cfg.get("sandbox") or meta.get("sandbox") or state.get("_sandbox")),
        "quality_gate": _qg if isinstance(_qg, dict) else {},
        "expected_outcomes": list(_eo) if isinstance(_eo, list) else [],
        "refactor_sop": _refactor_sop,
        "tdd_enforce": _tdd,
    }
    if _sm:
        stage_kw["sandbox_mode"] = _sm
    # E1: AGENT.md may declare architecture_profile / execution_backend.
    _ap = str(cfg.get("architecture_profile") or meta.get("architecture_profile") or "").strip()
    if _ap:
        stage_kw["architecture_profile"] = _ap
    _eb = str(cfg.get("execution_backend") or meta.get("execution_backend") or "").strip().lower()
    if _eb in ("llm", "agent") and not _ap:
        stage_kw["execution_backend"] = _eb
    stage = PipelineStageConfig(**stage_kw)
    if _ap:
        apply_architecture_profile(stage)
    apply_coding_stage_defaults(stage)

    # Policy profile: agent explicit → intensity resolve → karpathy_v1 for coding.
    explicit_prof = str(
        cfg.get("coding_policy_profile") or meta.get("coding_policy_profile") or ""
    ).strip().lower()
    if explicit_prof and explicit_prof not in ("",):
        if explicit_prof in ("off", "none", "minimal", "disabled"):
            # Still apply done_verify/testability; keep slim inject if ops asked off.
            state["_coding_policy_profile"] = "off"
        else:
            state["_coding_policy_profile"] = explicit_prof
    else:
        try:
            from core.harness.utils.coding_intensity import (
                intensity_to_policy_profile,
                resolve_coding_intensity,
            )

            inten = resolve_coding_intensity(
                explicit=cfg.get("coding_intensity") or meta.get("coding_intensity"),
                state=state,
                scope="workspace",
                default="full",
            )
            state["_coding_intensity"] = inten
            state["_coding_policy_profile"] = intensity_to_policy_profile(inten)
        except Exception:
            state["_coding_policy_profile"] = "karpathy_v1"

    if isinstance(stage.done_verify, dict):
        try:
            from core.harness.execution.done_verify import build_done_verify_config

            state["_done_verify"] = build_done_verify_config(
                quality_gate=getattr(stage, "quality_gate", None)
                if isinstance(getattr(stage, "quality_gate", None), dict)
                else (state.get("quality_gate") if isinstance(state.get("quality_gate"), dict) else None),
                expected_outcomes=list(getattr(stage, "expected_outcomes", None) or [])
                or (state.get("expected_outcomes") if isinstance(state.get("expected_outcomes"), list) else None),
                done_verify=stage.done_verify,
                review_gate=str(getattr(stage, "review_gate", "") or rg or ""),
            )
        except Exception:
            state["_done_verify"] = dict(stage.done_verify)
    state["review_gate"] = str(getattr(stage, "review_gate", "") or rg or "")
    if bool(getattr(stage, "sandbox", False)):
        state["_sandbox"] = True
        state["sandbox"] = True

    extra: List[str] = []
    for sid in list(getattr(stage, "required_skills", None) or []):
        s = str(sid).strip()
        if not s:
            continue
        bound = state.get("_bound_skill_ids")
        if not isinstance(bound, list):
            bound = []
            state["_bound_skill_ids"] = bound
        if s not in bound:
            bound.append(s)
            extra.append(s)
    state["_workspace_coding_defaults"] = True
    return extra


def resolve_upgrade_agent_type(
    stage: "PipelineStageConfig",
    state: Dict[str, Any],
    *,
    conversational: Any = None,
    plan_upgrade: Any = None,
) -> str:
    """Signal-based react → plan/reflection; upgrade_policy=off skips."""
    agent_type = str(getattr(stage, "agent_type", "") or "react")
    policy = str(getattr(stage, "upgrade_policy", "") or "signals").strip().lower()
    if policy in ("off", "none", "disabled"):
        return agent_type
    conv = conversational or frozenset(
        {"conversational", "rag", "plan", "plan_execute", "reflection", "review", "materials_chat"}
    )
    pup = plan_upgrade or frozenset({"plan", "plan_execute", "reflection"})
    if agent_type in conv or agent_type in pup:
        return agent_type
    is_retry = int(state.get("_auto_retry_count", 0) or 0) > 0 or int(state.get("iteration", 0) or 0) > 1
    has_errors = bool(state.get("issues") or state.get("_quick_check_issues"))
    large_th = 200 if policy == "aggressive" else 500
    is_large = len(str(state.get("description", "") or "")) > large_th
    if is_retry and (has_errors or policy == "aggressive"):
        return "plan"
    if is_large and int(state.get("iteration", 0) or 0) == 1:
        return "plan"
    if has_errors and not is_retry:
        return "reflection"
    return agent_type


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
    # T3a: optional skill subscription (empty = no filter). required_skills always forced.
    skill_allow_tags: List[str] = Field(default_factory=list)
    skill_allow_roles: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)  # per-stage tool whitelist for agent backend
    completeness_check: Optional[dict] = Field(default=None)  # {input_artifact, output_key, max_per_call}
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
    # AI refactor SOP (diagnosis/deps/plan/tdd/review/flag/rollback) without env var.
    refactor_sop: bool = False
    context_isolation: str = "shared"   # "shared" | "isolated"
    context_profile: str = "code"        # "minimal" | "code" | "debug" | "deep"
    # L2 — imported existing-code context (config-driven, generic: any stage may
    # declare it needs imported-repo context; engine reads state.imported_repo and
    # appends referenced-file full text + manifest + behavior prompt block).
    inject_imported_context: bool = False
    # L3 — merge strategy for imported-code modification (plan-app-factory-l3):
    # "full_rewrite" = L2 behavior (rewrite whole file, behavior contract prompt)
    # "incremental_merge" = only affected files, diff preview + human merge approval
    merge_strategy: str = "full_rewrite"
    merge_review_required: bool = False   # incremental_merge forces this (approval gate)
    # Phase 11 — config-driven post-execution (replaces hardcoded business logic in engine)
    chain_skill_after: str = ""          # Auto-execute another skill after this stage completes
    deploy_files_to_disk: bool = False   # Parse ## FILE: blocks from output, write to project dir
    deploy_files_target_dir: str = ""    # Override target. Empty = ~/.aiplat/apps/{pid}/current
    test_execution_mode: str = ""        # "pytest" | "agent_conversation" | "" — which test runner
    # v3.1 — architecture mode (config-driven, drives architecture_design output shape)
    # "code" = FastAPI/RESTful architecture | "agent" = Agent/skill-routing architecture | "" = auto/legacy
    architecture_mode: str = ""
    # Phase 12 — execution backend selection (replaces SOP detection / agent_type switching)
    execution_backend: str = "llm"       # "llm"=sys_llm_generate | "agent"=StageRunner.run()→ReActLoop
    # W2/B1 — optional architecture mix. When set, overrides execution_backend + agent_type.
    # oneshot | react_tools | plan_execute | reflect_loop | ""
    architecture_profile: str = ""
    # off = no runtime react→plan/reflection; signals = current default; aggressive = lower thresholds
    upgrade_policy: str = "signals"
    # v3.0 — capability profile: replaces binary execution_backend switch with declarative capability tiers.
    # "auto" = engine auto-infers from stage declarations (recommended)
    # "minimal" | "standard" | "full" | "autonomous" = manual override
    capability_profile: str = "auto"
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
    # ── Cost budget controller (per-stage) ──
    cost_budget_usd: float = 0.0     # 0 = unlimited; else stop/downgrade when stage cost reaches this
    cost_priority: str = "balanced"  # "balanced" | "minimize_cost" | "maximize_quality"
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
    quality_gate: Dict[str, Any] = Field(default_factory=lambda: {"min_output_length": 100})  # 4step-verified: engine.py:4650 使用
    """CRAG-style quality gate: {condition, fallback, final_fallback}"""
    done_verify: Dict[str, Any] = Field(default_factory=dict)
    """DONE-before Verify ring overlay (Harness first-class): {enabled, min_output_length,
    require_keys, require_substrings, expected_outcomes, reject_trivial_done,
    reject_action_envelope, require_commands}. Merged in StageRunner / ReActLoop."""
    meta_tool: Dict[str, Any] = Field(default_factory=dict)
    """Code meta-tool preference (Harness first-class): {enabled, auto_bind, force}.
    Maps to loop context _prefer_code_meta_tool / _meta_tool_auto_bind / _force_code_meta_tool."""
    routing_rules: Dict[str, Any] = Field(default_factory=dict)  # 4step-verified: wired via pipeline_compiler.py + engine.py:1900
    """Domain routing rules: {tiers, fallback_domain}"""
    retry_policy: Dict[str, Any] = Field(default_factory=lambda: {"max_retries": 2, "backoff": "exponential"})  # 4step-verified: engine.py:8306 使用
    """Self-heal retry: {on, action, max_retries}"""
    # ── v4.1: Cross-stage rollback (delegation + adversarial pattern) ──
    rollback_on_reject: bool = False
    """When evaluation REJECTED, rollback to upstream stage instead of same-stage retry."""
    rollback_target_id: str = ""
    """Target stage ID to rollback to when rejected (empty = use depends_on for upstream)."""
    # ── C0 frozen: stage schema gate + handoff envelope (empty schema = no-op) ──
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    """JSON-schema-like or field checklist for upstream artifacts before stage start."""
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    """JSON-schema-like or field checklist for this stage's output_artifact."""
    gate_on_fail: str = ""
    """Empty | block | hitl | fail_pipeline — empty keeps backward-compatible no hard gate."""
    handoff_required: bool = False
    """When true, stage output meta must include frozen handoff.* keys (see stage_handoff)."""
    # Phase B W3: factory contracted pipeline — disable DynamicOrchestrator free spawn
    allow_dynamic_spawn: bool = True
    """False = StageRunner skips sense_gap/spawn; factory stages force False via factory_profile."""

    @model_validator(mode="after")
    def _apply_architecture_profile(self) -> "PipelineStageConfig":
        # Also applies coding closed-loop defaults when uses_file_output.
        return apply_architecture_profile(self)


class PipelineConfig(BaseModel):
    stages: List[PipelineStageConfig] = Field(default_factory=list)
    max_iterations: int = 3
    max_tokens_per_run: int = 100000
    max_cost_per_run_usd: float = 0.0  # 0 = unlimited; else pipeline stops when cost reaches this
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
    app_name: str = ""  # canonical English slug (e.g. "video_parser") — established at creation, reused by all stages
    team_id: str = ""
    team_name: str = ""
    team_stages: List[PipelineStageConfig] = Field(default_factory=list)
    runs: List[ProjectRun] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class ProjectCreateRequest(BaseModel):
    name: str = ""
    description: str = ""
    app_name: str = ""  # optional: user-provided English slug; auto-derived if empty
    team_id: str = ""
    stages: List[Dict[str, Any]] = Field(default_factory=list)  # pre-built workflow stages
    factory_profile: str = "standard"  # F2a: standard | demo (project-level HITL profile)
    output_style: str = "default"  # A0: default | adhd (user-facing prose only)
    writing_profile: str = "concise_v1"  # concise_v1 | off — STE-inspired handoff/HITL prose (P0 default on)
    factory_mode: str = ""  # F2b: agent | code | hybrid | "" (auto / LLM)
    coding_intensity: str = ""  # B: lite | full | ultra | "" (resolve from mode/env)


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
