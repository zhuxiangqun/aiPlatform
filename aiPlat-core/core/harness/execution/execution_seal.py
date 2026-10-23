"""Execution seal helpers — platform completion contract (not Pi).

DONE-before: coding deliverable veto + ``check_done_verify``.
DONE-after: ``seal_answer_with_receipts`` (fix/path claims need tool receipts).

Shared by ReActLoop and PlanExecuteLoop so plan_execute cannot skip the
coding/review ring. Pi hybrid only tags Memory via its JS twin; see
``docs/architecture/execution-decision-matrix.md`` §2.6 and
``core/tests/unit/test_harness/test_completion_receipt.py``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_CODING_PRIMARY = frozenset({"code_generation", "code-hygiene", "file_operations"})
_FOLLOWUP_ORDER = ("autoreview", "code_review", "code-hygiene")


def seal_answer_with_receipts(
    text: str,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Bind fix/path claims to tool receipts. Returns ``(text, seal_status)``.

    ``seal_status`` is ``ok`` | ``unverified`` | ``failed``.
    """
    from core.harness.execution.completion_receipt import bind_completion_to_receipts

    ctx = context if isinstance(context, dict) else {}
    return bind_completion_to_receipts(str(text or ""), ctx)


def check_done_verify(context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Run ``run_done_verify``; coding/review paths fail-closed on exceptions."""
    ctx = context if isinstance(context, dict) else {}
    try:
        from core.harness.execution.done_verify import run_done_verify

        return run_done_verify(ctx)
    except Exception:
        logger.debug("done_verify seal helper skipped", exc_info=True)
        from core.harness.execution.done_verify import done_verify_exception_is_hard

        if done_verify_exception_is_hard(ctx):
            return (
                "done_verify: verify ring failed "
                "(exception; fail-closed for coding/review)"
            )
        return None


def is_coding_seal_context(context: Optional[Dict[str, Any]] = None) -> bool:
    """True when missing review / file delivery must not soft-pass."""
    from core.harness.execution.done_verify import done_verify_exception_is_hard

    return done_verify_exception_is_hard(context if isinstance(context, dict) else {})


def pending_coding_followup(
    context: Dict[str, Any],
    *,
    bound_skill_ids: Optional[Sequence[str]] = None,
    ensure_skill: Optional[Callable[[str], bool]] = None,
) -> Optional[str]:
    """Next review/hygiene skill after a substantial primary coding delivery.

    Driven by required_skills / done_verify (not agent_id). Prefer
    autoreview → code_review → code-hygiene. When ``require_review`` is on,
    schedule ``autoreview`` first — hygiene peers do not substitute.
    """
    ctx = context if isinstance(context, dict) else {}
    if bound_skill_ids is None:
        from core.harness.utils.execute_session import resolve_bound_skill_ids

        bound_skill_ids = resolve_bound_skill_ids(ctx)
    bound_s = {str(x).strip() for x in (bound_skill_ids or []) if str(x).strip()}
    done = ctx.get("_followup_skills_done") or []
    if not isinstance(done, list):
        done = []
    done_s = {str(x).strip() for x in done if str(x).strip()}
    dv = ctx.get("_done_verify") if isinstance(ctx.get("_done_verify"), dict) else {}
    if isinstance(dv, dict) and dv.get("require_review") and "autoreview" not in done_s:
        bound = list(ctx.get("_bound_skill_ids") or [])
        if "autoreview" not in bound:
            ctx["_bound_skill_ids"] = [*bound, "autoreview"]
        if ensure_skill is not None:
            try:
                ensure_skill("autoreview")
            except Exception:
                logger.debug("ensure autoreview for require_review skipped", exc_info=True)
        return "autoreview"
    for sid in _FOLLOWUP_ORDER:
        if sid in bound_s and sid not in done_s:
            return sid
    return None


def coding_deliverable_veto(
    context: Optional[Dict[str, Any]] = None,
    *,
    bound_skill_ids: Optional[Sequence[str]] = None,
    skills: Any = None,
    ensure_skill: Optional[Callable[[str], bool]] = None,
) -> Optional[str]:
    """Reject premature DONE for clarify-only / thin stubs / missing follow-up.

    After repeated coding vetoes, fail-open (return None) so eager finalize can
    seal; ``quality_review_blocks_success`` then flips status to failed.
    """
    ctx = context if isinstance(context, dict) else {}
    try:
        from core.management.execution_quality_review import (
            _input_asks_coding_delivery,
            is_non_deliverable_coding_output,
        )
    except Exception:
        return None

    if bound_skill_ids is None:
        from core.harness.utils.execute_session import resolve_bound_skill_ids

        bound_skill_ids = resolve_bound_skill_ids(ctx, skills)

    skill_once = str(ctx.get("_skill_delivery") or "").strip().lower() == "once"
    bound_s = {str(x).strip() for x in (bound_skill_ids or []) if str(x).strip()}
    coding_skills = bound_s & _CODING_PRIMARY
    in_text = str(ctx.get("_user_task") or "").strip()
    if not in_text:
        task = str(ctx.get("task") or "").strip()
        if "## Task\n" in task:
            in_text = task.split("## Task\n", 1)[1].strip()
        else:
            in_text = task
    asks = _input_asks_coding_delivery(in_text) if in_text else False
    if not (skill_once or coding_skills or asks):
        return None

    out = str(ctx.get("output") or "").strip()
    reason: Optional[str] = None

    if not out:
        if skill_once and not ctx.get("_primary_skill_delivered"):
            reason = (
                "skill_delivery=once requires a successful primary skill call "
                "(e.g. code_generation) before DONE — do not end with clarification"
            )
    else:
        try:
            from core.harness.utils.execute_session import looks_like_pending_action_envelope

            if looks_like_pending_action_envelope(out):
                ctx["_pseudo_tool"] = True
                reason = (
                    "output is still a skill_call/tool_call envelope — execute the skill "
                    "(do not DONE with the call JSON as the answer)"
                )
        except Exception:
            pass  # noqa: cleanup-best-effort

        if reason is None and skill_once and not ctx.get("_primary_skill_delivered"):
            reason = (
                "skill_delivery=once requires a successful primary skill call "
                "(e.g. code_generation) before DONE — do not end with clarification"
            )

        if reason is None and (coding_skills or asks) and is_non_deliverable_coding_output(
            input_text=in_text,
            output_text=out,
            raw_out={"text": out},
            hints=" ".join(sorted(bound_s)),
            scope="skill",
        ):
            reason = (
                "coding deliverable is clarify-only, thin DONE/## FILE stub, "
                "wrong language, or off-spec placeholder — "
                "call the bound skill and produce task-matching runnable code before DONE"
            )

        if reason is None and ctx.get("_primary_skill_delivered"):
            follow = pending_coding_followup(
                ctx,
                bound_skill_ids=list(bound_s),
                ensure_skill=ensure_skill,
            )
            if follow:
                reason = (
                    f"call bound follow-up skill `{follow}` on the generated files "
                    "before DONE"
                )

    if not reason:
        return None
    veto_n = int(ctx.get("_acceptance_veto_count", 0) or 0)
    followup_only = "follow-up skill" in reason or "followup skill" in reason
    limit = 2 if followup_only else 3
    if veto_n >= limit:
        ctx["_coding_veto_exhausted"] = True
        ctx["_coding_veto_last_reason"] = reason
        # Dev may soft-seal so quality_review can fail the stage; production /
        # AIPLAT_CODING_VETO_FAIL_CLOSED keeps vetoing (no incomplete green).
        fail_closed = (
            os.getenv("AIPLAT_CODING_VETO_FAIL_CLOSED", "").strip().lower()
            in ("1", "true", "yes", "on")
            or (os.getenv("AIPLAT_PROFILE") or "").strip().lower() == "production"
        )
        if os.getenv("AIPLAT_CODING_VETO_FAIL_OPEN", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            fail_closed = False
        if fail_closed:
            return reason
        return None
    return reason


def settle_repair_prediction(
    context: Optional[Dict[str, Any]] = None,
    *,
    blocked: bool = False,
) -> str:
    """Write predicted-vs-actual once, then re-seal if the measurement failed.

    No world model. ``blocked`` is a coding/done_verify veto. A failed seal
    or forced failure also counts as actual_pass false.
    """
    ctx = context if isinstance(context, dict) else {}
    seal = str(ctx.get("_completion_seal") or "ok")
    picked = ctx.get("_repair_candidate_selected")
    if not isinstance(picked, dict) or not picked.get("chosen") or ctx.get("_prediction_receipt"):
        return seal
    from core.harness.execution.completion_receipt import note_prediction_outcome

    force = str(ctx.get("_force_failed_status") or "").strip().lower()
    hard = bool(ctx.get("_finalize_hard_fail"))
    actual = (
        not blocked
        and not hard
        and seal == "ok"
        and force not in ("timeout", "failed", "error", "cancelled", "canceled")
    )
    chosen = picked.get("chosen") or {}
    note_prediction_outcome(
        ctx,
        predicted_pass=bool(picked.get("predicted_pass")),
        actual_pass=actual,
        candidate_id=str(chosen.get("id") or ""),
    )
    if not actual:
        text, seal = seal_answer_with_receipts(str(ctx.get("output") or ""), ctx)
        ctx["output"] = text
        ctx["_completion_seal"] = seal
    return seal


def seal_before_finish(
    context: Optional[Dict[str, Any]] = None,
    *,
    bound_skill_ids: Optional[Sequence[str]] = None,
    skills: Any = None,
    ensure_skill: Optional[Callable[[str], bool]] = None,
    bind_receipts: bool = True,
) -> Tuple[str, Optional[str]]:
    """Seal answer text and return ``(seal_status, block_reason)``.

    ``block_reason`` non-None means the loop must not FINISHED as success.
    Mutates ``context['output']`` when binding receipts.
    """
    ctx = context if isinstance(context, dict) else {}
    seal = "ok"
    if bind_receipts:
        text, seal = seal_answer_with_receipts(str(ctx.get("output") or ""), ctx)
        ctx["output"] = text
        ctx["_completion_seal"] = seal
    veto = coding_deliverable_veto(
        ctx,
        bound_skill_ids=bound_skill_ids,
        skills=skills,
        ensure_skill=ensure_skill,
    )
    if veto:
        return seal, veto
    block = check_done_verify(ctx)
    settle_repair_prediction(ctx, blocked=bool(block))
    seal = str(ctx.get("_completion_seal") or seal)
    return seal, block
