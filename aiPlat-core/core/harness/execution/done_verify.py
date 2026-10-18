"""DONE-before Verify ring — config-driven completion checks (Harness first-class).

Closes the article verify-loop gap: before the agent seals DONE, run
deterministic checks driven by ``quality_gate`` / ``expected_outcomes`` /
``_done_verify`` — not by agent_id string matching.

Production callers:
  - ReActLoop._acceptance_gate
  - StageRunner (injects config from PipelineStageConfig)
  - CoreFacade.run_workspace_agent (injects from AGENT.md metadata)
  - pipeline_engine._run_stage_skill (pre-deploy gate for llm + uses_file_output)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TRIVIAL_DONE = re.compile(
    r"^(DONE|FINAL|" + "\u5b8c\u6210|\u7ed3\u675f)[:\uff1a\\s]*$",
    re.IGNORECASE,
)


def done_verify_enabled(context: Optional[Dict[str, Any]] = None) -> bool:
    """Master switch. Env AIPLAT_DONE_VERIFY overrides; default on."""
    ctx = context if isinstance(context, dict) else {}
    cfg = ctx.get("_done_verify") if isinstance(ctx.get("_done_verify"), dict) else {}
    if "enabled" in cfg:
        return bool(cfg.get("enabled"))
    return os.getenv("AIPLAT_DONE_VERIFY", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def build_done_verify_config(
    *,
    quality_gate: Optional[Dict[str, Any]] = None,
    expected_outcomes: Optional[List[Dict[str, Any]]] = None,
    done_verify: Optional[Dict[str, Any]] = None,
    review_gate: str = "",
) -> Dict[str, Any]:
    """Merge PipelineStageConfig / AGENT.md fields into a single ``_done_verify`` dict."""
    qg = quality_gate if isinstance(quality_gate, dict) else {}
    overlay = done_verify if isinstance(done_verify, dict) else {}
    min_len = overlay.get("min_output_length")
    if min_len is None:
        min_len = qg.get("min_output_length")
    try:
        min_len_i = int(min_len) if min_len is not None else 0
    except (TypeError, ValueError):
        min_len_i = 0
    eo = overlay.get("expected_outcomes")
    if eo is None:
        eo = expected_outcomes
    if not isinstance(eo, list):
        eo = []
    out: Dict[str, Any] = {
        "enabled": bool(overlay.get("enabled", True)),
        "min_output_length": max(0, min_len_i),
        "expected_outcomes": [x for x in eo if isinstance(x, dict)],
        "reject_action_envelope": bool(overlay.get("reject_action_envelope", True)),
        "reject_trivial_done": bool(overlay.get("reject_trivial_done", True)),
        "require_keys": [
            str(k).strip()
            for k in (overlay.get("require_keys") or [])
            if str(k).strip()
        ],
        "require_substrings": [
            str(s)
            for s in (overlay.get("require_substrings") or overlay.get("require_substring") or [])
            if str(s).strip()
        ],
        "review_gate": str(overlay.get("review_gate") or review_gate or "").strip().lower(),
        "require_commands": [
            str(c).strip()
            for c in (overlay.get("require_commands") or [])
            if str(c).strip()
        ][:8],
        # P1 testability: core handlers need pure unit tests (not integration-only).
        "require_testability": bool(overlay.get("require_testability", False)),
        "testability_mode": str(overlay.get("testability_mode") or "").strip().lower(),
        # Refactor SOP Step 4: a passing test receipt before DONE (PipelineStageConfig.tdd_enforce).
        "require_tdd": bool(overlay.get("require_tdd", False)),
        # Refactor SOP Step 1: a severity-tagged problem list, not a code dump.
        "require_diagnosis": bool(overlay.get("require_diagnosis", False)),
        # Refactor SOP Step 3: confirmed plan before code (small-step refactor).
        "require_refactor_plan": bool(overlay.get("require_refactor_plan", False)),
        # Refactor SOP Step 2: safe vs protected dependency zones named explicitly.
        "require_dependency_map": bool(overlay.get("require_dependency_map", False)),
        # Refactor SOP Step 7: a rollback tag or file checkpoint before DONE.
        "require_rollback_checkpoint": bool(overlay.get("require_rollback_checkpoint", False)),
        # Refactor SOP Step 7b: a one-click rollback command written down.
        "require_rollback_command": bool(overlay.get("require_rollback_command", False)),
        # Refactor SOP Step 6: feature flag / canary switch named before DONE.
        "require_feature_flag": bool(overlay.get("require_feature_flag", False)),
        # Refactor SOP Step 5: adversarial review must run (not silent no-op).
        "require_review": bool(overlay.get("require_review", False)),
        "require_completion_standard": bool(overlay.get("require_completion_standard", False)),
        "output_schema": overlay.get("output_schema") if isinstance(overlay.get("output_schema"), dict) else {},
    }
    return out


_TEST_RUN_MARKERS = (
    "pytest",
    "npm test",
    "npm run test",
    "pnpm test",
    "yarn test",
    "jest",
    "vitest",
    "go test",
    "cargo test",
    "python -m unittest",
)
_SHELL_TOOLS = frozenset({
    "bash",
    "shell",
    "sh",
    "terminal",
    "exec",
    "execute",
    "run",
    "command",
    "sys_terminal",
    "code_execution",
    "codeexecution",
})


_DIAGNOSIS_MARK = re.compile(r"\[P[012]\]", re.IGNORECASE)

# CJK/locale patterns live in locale_markers (engine §78b).
from core.harness.utils.locale_markers import (  # noqa: E402
    FEATURE_FLAG_RE as _FEATURE_FLAG_MARK,
    MSG_DEP_MAP_REQUIRED,
    MSG_FEATURE_FLAG_REQUIRED,
    MSG_PLAN_REQUIRED,
    MSG_ROLLBACK_CMD_REQUIRED,
    PLAN_HEAD_RE as _PLAN_HEAD,
    PROTECTED_ZONE_RE as _PROTECTED_ZONE,
    ROLLBACK_CMD_RE as _ROLLBACK_CMD,
    SAFE_ZONE_RE as _SAFE_ZONE,
)

_ROLLBACK_MARK = re.compile(
    r"(?i)(?:before-refactor|pre-refactor|file_checkpoint|"
    r"git\s+tag|rollback\s+(?:tag|checkpoint|command))"
)


def _turn_text_blob(context: Dict[str, Any]) -> str:
    ctx = context if isinstance(context, dict) else {}
    blobs = [str(ctx.get("output") or ""), str(ctx.get("result") or "")]
    for row in ctx.get("_tool_receipts") or []:
        if isinstance(row, dict):
            blobs.append(str(row.get("detail") or ""))
    return "\n".join(blobs)


def diagnosis_list_missing(context: Dict[str, Any]) -> Optional[str]:
    """None when the turn already states a [P0]/[P1]/[P2] problem list."""
    if _DIAGNOSIS_MARK.search(_turn_text_blob(context)):
        return None
    return "done_verify: diagnosis list required — include [P0], [P1], or [P2] before DONE"


def refactor_plan_missing(context: Dict[str, Any]) -> Optional[str]:
    """None when the turn includes an explicit refactor plan heading."""
    if _PLAN_HEAD.search(_turn_text_blob(context)):
        return None
    return MSG_PLAN_REQUIRED


def dependency_map_missing(context: Dict[str, Any]) -> Optional[str]:
    """None when both a safe zone and a protected zone are named."""
    text = _turn_text_blob(context)
    if _SAFE_ZONE.search(text) and _PROTECTED_ZONE.search(text):
        return None
    return MSG_DEP_MAP_REQUIRED


def rollback_checkpoint_missing(context: Dict[str, Any]) -> Optional[str]:
    """None when a file checkpoint id or explicit rollback tag is present."""
    ctx = context if isinstance(context, dict) else {}
    rows = ctx.get("_file_checkpoints")
    if isinstance(rows, list) and any(
        isinstance(r, dict) and str(r.get("id") or "").strip() for r in rows
    ):
        return None
    if _ROLLBACK_MARK.search(_turn_text_blob(ctx)):
        return None
    return (
        "done_verify: rollback checkpoint required — "
        "overwrite via sys_file_* (auto checkpoint) or record a git tag / before-refactor marker"
    )


def feature_flag_missing(context: Dict[str, Any]) -> Optional[str]:
    """None when a feature flag / canary switch is named in the turn."""
    if _FEATURE_FLAG_MARK.search(_turn_text_blob(context)):
        return None
    return MSG_FEATURE_FLAG_REQUIRED


def rollback_command_missing(context: Dict[str, Any]) -> Optional[str]:
    """None when a one-click rollback command is written in the turn."""
    if _ROLLBACK_CMD.search(_turn_text_blob(context)):
        return None
    return MSG_ROLLBACK_CMD_REQUIRED


def _test_command_blob(row: Dict[str, Any]) -> str:
    """Command text only. A file read that mentions pytest is not a test run."""
    command = " ".join(str(row.get(k) or "") for k in ("command", "cmd")).strip().lower()
    if command:
        return command
    tool = str(row.get("tool") or row.get("name") or "").strip().lower()
    shell = tool in _SHELL_TOOLS or tool.endswith("terminal") or "bash" in tool
    if not shell:
        return ""
    return str(row.get("detail") or "").strip().lower()


def _test_receipt_passed(row: Dict[str, Any]) -> bool:
    """Failed status wins over a zero exit code."""
    status = str(row.get("status") or "").strip().lower()
    if status in ("failed", "error", "fail"):
        return False
    code = row.get("exit_code", row.get("returncode"))
    if code is not None and code != 0 and str(code) != "0":
        return False
    if status in ("ok", "success", "passed", "completed"):
        return True
    return code == 0 or str(code) == "0"


def tdd_evidence_missing(context: Dict[str, Any]) -> Optional[str]:
    """None only when every test-runner receipt this turn passed.

    A later failed pytest still blocks DONE. Mentions of a runner inside a
    file-read receipt do not count.
    """
    receipts = context.get("_tool_receipts") if isinstance(context, dict) else None
    if not isinstance(receipts, list):
        return "done_verify: tdd_enforce — run tests for the changed code before DONE"
    saw_pass = False
    saw_fail = False
    for row in receipts:
        if not isinstance(row, dict):
            continue
        blob = _test_command_blob(row)
        if not blob or not any(m in blob for m in _TEST_RUN_MARKERS):
            continue
        if _test_receipt_passed(row):
            saw_pass = True
        else:
            saw_fail = True
    if saw_fail:
        return "done_verify: tdd_enforce — test run failed; fix before DONE"
    if saw_pass:
        return None
    return "done_verify: tdd_enforce — run tests for the changed code before DONE"


def _has_completion_standard(cfg: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """A delivery may finish only when a checkable standard is configured.

    Length alone is not a standard. Chat turns leave the flag off.
    """
    if cfg.get("expected_outcomes") or cfg.get("require_keys") or cfg.get("require_substrings"):
        return True
    if cfg.get("require_commands"):
        return True
    for src in (cfg.get("output_schema"), context.get("output_schema"), context.get("_output_schema")):
        if isinstance(src, dict) and src:
            return True
    return False


def stage_verify_context(stage: Any) -> Dict[str, Any]:
    """Stage-level ``output_schema`` counts as a completion standard."""
    schema = getattr(stage, "output_schema", None) if stage is not None else None
    if isinstance(schema, dict) and schema:
        return {"output_schema": schema}
    return {}


def missing_completion_standard_reason(stage: Any) -> Optional[str]:
    """File-output stages refuse to start when no checkable standard is configured.

    Chat and non-file stages leave the flag off. Length is not a standard.
    """
    if stage is None or not bool(getattr(stage, "uses_file_output", False)):
        return None
    try:
        from core.schemas_builder import apply_coding_stage_defaults

        apply_coding_stage_defaults(stage)
    except Exception:
        logger.debug("coding stage defaults skipped", exc_info=True)
    dv = getattr(stage, "done_verify", None)
    qg = getattr(stage, "quality_gate", None)
    eo = getattr(stage, "expected_outcomes", None)
    cfg = build_done_verify_config(
        quality_gate=qg if isinstance(qg, dict) else None,
        expected_outcomes=list(eo) if isinstance(eo, list) else None,
        done_verify=dv if isinstance(dv, dict) else None,
        review_gate=str(getattr(stage, "review_gate", "") or ""),
    )
    if cfg.get("require_completion_standard") and not _has_completion_standard(
        cfg, stage_verify_context(stage)
    ):
        return (
            "done_verify: delivery requires a completion standard "
            "(expected_outcomes, output_schema, require_keys, require_substrings, or require_commands)"
        )
    return None


_CODING_BOUND_SKILL_IDS = frozenset(
    {
        "code_generation",
        "code-hygiene",
        "file_operations",
        "autoreview",
        "code_review",
    }
)


def done_verify_exception_is_hard(context: Optional[Dict[str, Any]] = None) -> bool:
    """True when a crashed verify ring must not be treated as pass.

    Shared by ReActLoop, PlanExecuteLoop, and StageRunner inject fail-closed.
    """
    ctx = context if isinstance(context, dict) else {}
    dv = ctx.get("_done_verify") if isinstance(ctx.get("_done_verify"), dict) else {}
    if dv.get("require_review") or dv.get("require_completion_standard"):
        return True
    if str(ctx.get("_skill_delivery") or "").strip().lower() == "once":
        return True
    bound_raw = ctx.get("_bound_skill_ids") or []
    if not isinstance(bound_raw, (list, tuple, set)):
        bound_raw = []
    bound = {str(x).strip() for x in bound_raw if str(x).strip()}
    return bool(bound & _CODING_BOUND_SKILL_IDS)


def is_hard_done_veto(reason: str, context: Optional[Dict[str, Any]] = None) -> bool:
    """Vetoes that must not fail-open after repeated attempts.

    Completion-standard gaps always stay hard. Missing review receipts stay hard
    too — whether via ``require_review`` (SOP Step 5) or soft ``review_gate=…``
    requiring a follow-up skill — so two soft vetoes cannot greenwash DONE.
    """
    text = str(reason or "")
    if text.startswith("done_verify: delivery requires a completion standard"):
        return True
    if "is not a review receipt" in text or "not an autoreview receipt" in text:
        return True
    if text.startswith("done_verify: review_gate=") and "requires follow-up skill" in text:
        return True
    if text.startswith("done_verify: require_review"):
        return True
    if text.startswith("done_verify: verify ring failed"):
        return True
    # Refactor SOP checks stay hard. Two soft vetoes must not seal DONE
    # without a passing test, diagnosis, plan, zones, rollback, or flag.
    if text.startswith((
        "done_verify: tdd_enforce",
        "done_verify: diagnosis list",
        "done_verify: refactor plan",
        "done_verify: dependency map",
        "done_verify: rollback checkpoint",
        "done_verify: rollback command",
        "done_verify: feature flag",
    )):
        return True
    ctx = context if isinstance(context, dict) else {}
    dv = ctx.get("_done_verify") if isinstance(ctx.get("_done_verify"), dict) else {}
    if dv.get("require_review") and text.startswith("done_verify: review_gate="):
        return True
    return False


def resolve_done_verify_config(context: Dict[str, Any]) -> Dict[str, Any]:
    """Read ``_done_verify`` from loop context, filling defaults from ``quality_gate``."""
    ctx = context if isinstance(context, dict) else {}
    existing = ctx.get("_done_verify") if isinstance(ctx.get("_done_verify"), dict) else {}
    qg = ctx.get("quality_gate") if isinstance(ctx.get("quality_gate"), dict) else {}
    eo = ctx.get("expected_outcomes") if isinstance(ctx.get("expected_outcomes"), list) else None
    return build_done_verify_config(
        quality_gate=qg,
        expected_outcomes=eo,
        done_verify=existing,
        review_gate=str(ctx.get("review_gate") or existing.get("review_gate") or ""),
    )


def _default_min_len(cfg: Dict[str, Any]) -> int:
    if int(cfg.get("min_output_length") or 0) > 0:
        return int(cfg["min_output_length"])
    try:
        return max(0, int(os.getenv("AIPLAT_DONE_VERIFY_MIN_LEN", "20") or 20))
    except (TypeError, ValueError):
        return 20


def run_done_verify(context: Dict[str, Any]) -> Optional[str]:
    """Return veto reason string, or None if completion may proceed.

    Deterministic only — no LLM. Coding-specific substance checks stay in
    ``ReActLoop._coding_deliverable_veto`` (still called first).
    """
    if not isinstance(context, dict):
        return None
    if not done_verify_enabled(context):
        return None

    cfg = resolve_done_verify_config(context)
    if not cfg.get("enabled", True):
        return None

    if cfg.get("require_completion_standard") and not _has_completion_standard(cfg, context):
        return (
            "done_verify: delivery requires a completion standard "
            "(expected_outcomes, output_schema, require_keys, require_substrings, or require_commands)"
        )

    try:
        from core.harness.execution.completion_receipt import apply_repair_selection

        selection_error = apply_repair_selection(context)
        if selection_error:
            return f"done_verify: {selection_error}"
    except Exception:
        if done_verify_exception_is_hard(context):
            return (
                "done_verify: repair candidate selection failed "
                "(exception; fail-closed for coding/review)"
            )
        logger.debug("repair candidate selection skipped", exc_info=True)

    output = str(context.get("output") or "").strip()

    if cfg.get("reject_action_envelope", True) and output:
        try:
            from core.harness.utils.execute_session import looks_like_pending_action_envelope

            if looks_like_pending_action_envelope(output):
                context["_pseudo_tool"] = True
                return (
                    "done_verify: output is still a skill_call/tool_call envelope — "
                    "execute the action before DONE"
                )
        except Exception:
            logger.debug("done_verify envelope check skipped", exc_info=True)

    if cfg.get("reject_trivial_done", True) and output and _TRIVIAL_DONE.match(output):
        return "done_verify: trivial DONE/FINAL with no answer body"

    min_len = _default_min_len(cfg)
    if min_len > 0 and len(output) < min_len:
        if not output:
            context["_output_empty"] = True
        return (
            f"done_verify: output length {len(output)} < min_output_length={min_len}"
        )

    keys = cfg.get("require_keys") or []
    if keys:
        parsed: Any = None
        try:
            parsed = json.loads(output)
        except Exception:
            parsed = None
        if not isinstance(parsed, dict):
            return "done_verify: output is not JSON object but require_keys is set"
        missing = [k for k in keys if k not in parsed or parsed.get(k) in (None, "", [], {})]
        if missing:
            return "done_verify: missing required keys: " + ", ".join(missing[:8])

    for needle in cfg.get("require_substrings") or []:
        if needle and needle not in output:
            return f"done_verify: required marker missing: {needle[:80]}"

    outcomes = cfg.get("expected_outcomes") or []
    if outcomes:
        try:
            from core.harness.execution.verification import verify_against_expected

            artifact: Any = output
            try:
                artifact = json.loads(output)
            except Exception:
                artifact = {"text": output, "output": output}
            result = verify_against_expected(artifact, outcomes, stage_id="done_verify")
            if not result.verified:
                fail = (result.failures or [{}])[0]
                return (
                    "done_verify: expected_outcomes failed: "
                    f"{fail.get('field')}:{fail.get('error') or fail.get('constraint')}"
                )[:240]
        except Exception:
            logger.debug("done_verify expected_outcomes skipped", exc_info=True)

    # Peer-review gate (article: second-model review). Soft path: only when a review
    # skill is already bound. Hard path (require_review / SOP Step 5): always
    # demand autoreview (or bound peer) before DONE — never silent no-op.
    # review_gate=none and _review_gate_passed do not waive the hard path.
    rg = str(cfg.get("review_gate") or "").strip().lower()
    if cfg.get("require_review") and rg in ("", "off", "none", "false", "0", "no"):
        rg = "quick"
    if rg and rg not in ("off", "none", "false", "0", "no"):
        bound = {
            str(x).strip()
            for x in (context.get("_bound_skill_ids") or [])
            if str(x).strip()
        }
        peer = ("autoreview", "code_review", "code-hygiene")
        if rg in ("required", "quick", "deep", "true", "1", "yes", "on"):
            want = [s for s in peer if s in bound]
        else:
            want = [rg] if rg in bound else []
        if cfg.get("require_review"):
            # SOP Step 5 names autoreview. code-hygiene / code_review do not substitute.
            if context.get("_require_review_incomplete"):
                return (
                    "done_verify: require_review — autoreview receipt was rejected "
                    "(approval hold or empty diff)"
                )
            want = ["autoreview"]
        if want:
            done_raw = context.get("_followup_skills_done") or []
            done_s = {str(x).strip() for x in done_raw if str(x).strip()} if isinstance(done_raw, list) else set()
            if context.get("_review_gate_passed") and not cfg.get("require_review"):
                pass
            elif not any(s in done_s for s in want):
                return (
                    f"done_verify: review_gate={rg} requires follow-up skill "
                    f"`{want[0]}` before DONE"
                )

    # Opt-in shell checks (article: run tests before sealing DONE). Fail-open if unset.
    cmds = cfg.get("require_commands") or []
    if cmds:
        import subprocess
        import shlex

        def _note_repair_measurement(*, actual_pass: bool) -> None:
            if not isinstance(context, dict):
                return
            try:
                from core.harness.execution.completion_receipt import (
                    note_prediction_outcome,
                )

                note_prediction_outcome(
                    context,
                    predicted_pass=True,
                    actual_pass=actual_pass,
                    candidate_id="require_commands",
                )
            except Exception:
                logger.debug("require_commands measurement note skipped", exc_info=True)

        cwd = str(context.get("cwd") or context.get("workdir") or os.getcwd())
        for cmd in cmds:
            try:
                proc = subprocess.run(  # noqa: S603 — intentional verify ring; cmd from config
                    shlex.split(cmd) if isinstance(cmd, str) else list(cmd),
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=min(120, int(os.getenv("AIPLAT_DONE_VERIFY_CMD_TIMEOUT", "60") or 60)),
                    check=False,
                )
            except Exception as e:
                return f"done_verify: require_commands failed to run ({cmd[:60]}): {e}"[:240]
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()[:120]
                _note_repair_measurement(actual_pass=False)
                return (
                    f"done_verify: require_commands exit {proc.returncode}: {cmd[:60]}"
                    + (f" — {err}" if err else "")
                )[:240]
        _note_repair_measurement(actual_pass=True)

    if cfg.get("require_diagnosis"):
        diag = diagnosis_list_missing(context)
        if diag:
            return diag

    if cfg.get("require_refactor_plan"):
        plan = refactor_plan_missing(context)
        if plan:
            return plan

    if cfg.get("require_dependency_map"):
        deps = dependency_map_missing(context)
        if deps:
            return deps

    if cfg.get("require_rollback_checkpoint"):
        rb = rollback_checkpoint_missing(context)
        if rb:
            return rb

    if cfg.get("require_rollback_command"):
        rcmd = rollback_command_missing(context)
        if rcmd:
            return rcmd

    if cfg.get("require_feature_flag"):
        ff = feature_flag_missing(context)
        if ff:
            return ff

    if cfg.get("require_tdd"):
        tdd_reason = tdd_evidence_missing(context)
        if tdd_reason:
            return tdd_reason

    # P1: testability gate — handlers need pure I/O unit tests (not full-stack).
    if cfg.get("require_testability"):
        try:
            from core.harness.meta.testability_gate import (
                collect_files_from_context,
                evaluate_files,
                veto_reason_from_report,
            )

            files = collect_files_from_context(context)
            if files:
                tmode = str(cfg.get("testability_mode") or "").strip().lower()
                report = evaluate_files(files, mode_override=tmode)
                context["_testability_report"] = report.to_dict()
                if report.findings and report.mode == "warn":
                    logger.info(
                        "done_verify testability warn: %s",
                        "; ".join(f.code for f in report.findings[:4]),
                    )
                veto = veto_reason_from_report(report)
                if veto:
                    return veto
        except Exception:
            logger.debug("done_verify testability check skipped", exc_info=True)

    return None


def gate_llm_file_output_stage(
    *,
    stage: Any,
    state: Dict[str, Any],
    result: str,
    artifact_key: str = "",
    backend: str = "llm",
) -> Optional[str]:
    """Pre-deploy DONE verify for ``execution_backend=llm`` + ``uses_file_output``.

    Agent/ReAct paths already call ``run_done_verify`` via ``_acceptance_gate``.
    The llm skill path writes ``## FILE:`` blobs then may ``_deploy_result_files``
    without that ring — this closes the hole (config-driven; no agent_id branches).

    Soft ``review_gate`` is skipped here: llm backend has no follow-up skill loop.
    Hard ``require_review`` (SOP Step 5) cannot be skipped — oneshot llm cannot
    produce an autoreview receipt, so deploy is vetoed. Use
    ``execution_backend=agent`` when peer-review before DONE is required.
    Fix/path claims without a successful tool receipt also veto (the file blob
    is not prefixed — a prefix would corrupt ``## FILE:`` deploy).
    """
    if not isinstance(state, dict):
        return None
    backend_n = str(backend or getattr(stage, "execution_backend", "") or "llm").strip().lower()
    if backend_n in ("agent", "react", "stage_runner"):
        return None
    if not bool(getattr(stage, "uses_file_output", False)):
        return None

    from core.schemas_builder import apply_coding_stage_defaults

    apply_coding_stage_defaults(stage)
    dv = getattr(stage, "done_verify", None)
    if not isinstance(dv, dict):
        dv = {}
    # Soft review_gate needs a tool loop — do not false-veto oneshot llm stages.
    # Hard require_review cannot be satisfied here; veto after the other checks.
    dv_gate = dict(dv)
    hard_review = bool(dv_gate.get("require_review"))
    dv_gate["review_gate"] = "none"
    dv_gate["require_review"] = False
    cfg = build_done_verify_config(
        quality_gate=getattr(stage, "quality_gate", None)
        if isinstance(getattr(stage, "quality_gate", None), dict)
        else None,
        expected_outcomes=list(getattr(stage, "expected_outcomes", None) or []) or None,
        done_verify=dv_gate,
        review_gate="none",
    )
    if not cfg.get("enabled", True):
        return None

    key = str(artifact_key or getattr(stage, "output_artifact", "") or "").strip()
    art = state.get(key) if key else None
    ctx: Dict[str, Any] = {
        "output": str(result or ""),
        "raw_output": str(result or ""),
        "_done_verify": cfg,
        "artifact": art if isinstance(art, dict) else {"raw_output": str(result or "")},
        "last_artifact": art if isinstance(art, dict) else None,
    }
    if key and isinstance(art, dict):
        ctx[key] = art
    if isinstance(art, dict) and isinstance(art.get("files"), list):
        ctx["files"] = art.get("files")
    cwd = str(state.get("_deploy_files_dir") or state.get("output_dir") or "").strip()
    if cwd:
        ctx["cwd"] = cwd
        ctx["workdir"] = cwd
    ctx.update(stage_verify_context(stage))

    veto = run_done_verify(ctx)
    picked = ctx.get("_repair_candidate_selected")
    chosen = ""
    if isinstance(picked, dict):
        chosen = str((picked.get("chosen") or {}).get("text") or "")
    if chosen.strip():
        state["output"] = chosen
        state["_selected_repair_output"] = chosen
        state["_repair_candidate_selected"] = picked
        if key and isinstance(state.get(key), dict):
            state[key]["raw_output"] = chosen
    if not veto and hard_review:
        veto = (
            "done_verify: require_review — llm backend has no autoreview follow-up; "
            "use execution_backend=agent"
        )
    # Do not prefix ## FILE: blobs (that would corrupt deploy). A fix/path
    # claim with no successful tool receipt fails the stage instead.
    if not veto:
        from core.harness.execution.execution_seal import seal_answer_with_receipts

        _seal_body = chosen or str(result or "")
        _sealed, _seal_st = seal_answer_with_receipts(_seal_body, state)
        if _seal_st != "ok":
            veto = (
                "done_verify: completion receipt "
                f"{_seal_st} — llm file output is not backed by a successful tool receipt"
            )
            state["_completion_seal"] = _seal_st
    if veto:
        state["_done_verify_last_reason"] = veto
        state["_done_verify_veto_count"] = int(state.get("_done_verify_veto_count", 0) or 0) + 1
        if isinstance(ctx.get("_testability_report"), dict):
            state["_testability_report"] = ctx["_testability_report"]
        if key and isinstance(state.get(key), dict):
            state[key]["status"] = "failed"
            state[key]["done_verify_veto"] = veto
    return veto
