"""DONE-before Verify ring — config-driven completion checks (Harness first-class).

Closes the article verify-loop gap: before the agent seals DONE, run
deterministic checks driven by ``quality_gate`` / ``expected_outcomes`` /
``_done_verify`` — not by agent_id string matching.

Production callers:
  - ReActLoop._acceptance_gate
  - StageRunner (injects config from PipelineStageConfig)
  - CoreFacade.run_workspace_agent (injects from AGENT.md metadata)
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
    }
    return out


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

    output = str(context.get("output") or "").strip()

    if cfg.get("reject_action_envelope", True) and output:
        try:
            from core.harness.utils.execute_session import looks_like_pending_action_envelope

            if looks_like_pending_action_envelope(output):
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

    # Peer-review gate (article: 另一模型评审). Deterministic — only when the
    # agent actually binds a review skill; does not invent agent_id branches.
    rg = str(cfg.get("review_gate") or "").strip().lower()
    if rg and rg not in ("off", "none", "false", "0", "no"):
        bound = {
            str(x).strip()
            for x in (context.get("_bound_skill_ids") or [])
            if str(x).strip()
        }
        if rg in ("required", "quick", "deep", "true", "1", "yes", "on"):
            want = [s for s in ("autoreview", "code_review", "code-hygiene") if s in bound]
        else:
            want = [rg] if rg in bound else []
        if want:
            done_raw = context.get("_followup_skills_done") or []
            done_s = {str(x).strip() for x in done_raw if str(x).strip()} if isinstance(done_raw, list) else set()
            if context.get("_review_gate_passed"):
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
                return (
                    f"done_verify: require_commands exit {proc.returncode}: {cmd[:60]}"
                    + (f" — {err}" if err else "")
                )[:240]

    return None
