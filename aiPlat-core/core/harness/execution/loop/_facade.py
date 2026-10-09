"""

ReActLoop — main execution loop facade.



Coordinates: reason → act → observe cycle.

Heavy lifting delegated to sub-modules (extracted for SRP per §5.75):

  - .inference.reason()

  - .state_mgr.{persist,apply,load,restate}_*

  - .compressor.{compact_messages,apply_context_shaping}

  - .graph_injector.{inject_graph_context,inject_memory_reminders}

"""

from typing import Any, Dict, List, Optional, Tuple

import asyncio

import json

import logging

import os

import re

import time

import uuid



from core.harness.memory.compression import _background_tool_summarize



from .base import BaseLoop, _infer_task_type, _extract_deny

from ...interfaces.loop import (

    ILoop, LoopState, LoopStateEnum, LoopConfig, LoopResult,

)

from ...infrastructure.hooks import HookManager, HookPhase, HookContext

from ..tool_calling import parse_action_call, parse_tool_call

from ...syscalls import sys_llm_generate, sys_skill_call, sys_tool_call

from ...assembly import PromptAssembler, ContextAssembler, ContextSource

from ...kernel.runtime import get_kernel_runtime



# ── Delegates ──

from .inference import reason

from .state_mgr import (

    persist_run_state, apply_todo_done_markers,

    load_run_state_for_prompt, restate_and_persist_run_state,

)

from .compressor import compact_messages, apply_context_shaping

from .graph_injector import inject_graph_context, inject_memory_reminders, inject_ontology_context





class ReActLoop(BaseLoop):

    """

    ReAct (Reasoning + Acting) Execution Loop

    

    Implements the ReAct pattern:

    - Reasoning: LLM decides what action to take

    - Acting: Execute the action (Skill or Tool)

    - Observing: Process the result

    

    Skill vs Tool distinction:

    - Skill: Internal capability, executed within Agent (e.g., text generation, code analysis)

    - Tool: External interface, called outside Agent (e.g., API, database, web search)

    """



    def __init__(

        self,

        config: Optional[LoopConfig] = None,

        hook_manager: Optional[HookManager] = None,

        model: Optional[Any] = None,

        skills: Optional[List[Any]] = None,

        tools: Optional[List[Any]] = None,

        approval_manager: Optional[Any] = None

    ):

        super().__init__(config, hook_manager)

        self._model = model

        self._skills = skills or []

        self._tools = tools or []

        self._approval_manager = approval_manager

        self._current_node = "reason"

        self._quality_history: List[Any] = []

        self._iters_since_skill: int = 0

        self._iters_since_memory: int = 0



        # PR #2: inject ControlProfile into _config for get_active_profile() to read

        if hasattr(self._config, "__dict__"):

            try:

                from core.harness.meta.profile_registry import get_active_profile

                self._config.control_profile = get_active_profile()

            except (ImportError, AttributeError):

                self._config.control_profile = None



    def _update_streak(self, action_result: Any) -> None:

        """Track consecutive 'not found' failures for stagnation detection."""

        self._not_found_streak = getattr(self, '_not_found_streak', 0)

        if action_result and "not found" in str(action_result).lower():

            self._not_found_streak += 1

        else:

            self._not_found_streak = 0



    def _detect_quality_drift(self, reasoning: str, state: LoopState) -> Tuple[bool, str]:

        if not isinstance(reasoning, str) or not reasoning.strip():

            return False, ""

        try:

            from core.harness.evaluation.drift_detector import DriftDetector

            snapshot = DriftDetector.capture_snapshot(reasoning, state.step_count)

            self._quality_history.append(snapshot)

            if len(self._quality_history) > DriftDetector.WINDOW_SIZE * 2:

                self._quality_history = self._quality_history[-DriftDetector.WINDOW_SIZE * 2:]

            return DriftDetector.check_drift(self._quality_history)

        except Exception:

            return False, ""



    async def _anti_divergence_action(self, reason: str, state: LoopState) -> str:

        prev = state.context.get("_drift_injection_count", 0)

        if prev >= 2:

            return "terminate"

        state.context["_drift_injection_count"] = prev + 1

        correction = f"SYSTEM REMINDER: quality decline detected ({reason}). Re-evaluate your approach."

        state.context.setdefault("messages", []).append({"role": "user", "content": correction})

        # Auto-record entropy for production readiness tracking

        try:

            from core.harness.evaluation.drift_detector import DriftDetector

            agent_id = state.context.get("_agent_id", "")

            DriftDetector.record_entropy(

                agent_id=str(agent_id),

                drift_type="quality_drift",

                severity="warning",

                description=reason,

            )

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        return "continue"



    def _acceptance_gate(self, state: LoopState) -> Optional[str]:

        """Deterministic acceptance veto over an LLM 'done' claim (Hermes Phase Gate).



        Reuses the ActiveChangeContract captured from the last coding skill

        (`syscalls/skill.py` → `set_active_change_contract`). If the agent claims

        completion but the artifacts it promised do not exist on disk, the claim

        is vetoed and the loop continues. Returns a veto reason, or None to allow.



        Design (CLAUDE.md §5.16: Harness owns protocol-level completion checks):

        - Only *file-verifiable* promises are checked (changed_files + path-like

          acceptance_criteria). Free-text criteria are NOT vetoed → no false

          positives. Runs with no active contract are unaffected (backward compat).

        - `AIPLAT_ACCEPTANCE_GATE_ENABLED=false` disables the gate entirely.

        """

        if os.getenv("AIPLAT_ACCEPTANCE_GATE_ENABLED", "true").lower() in ("0", "false", "no"):

            return None

        # Coding substance gate is independent of file-contract fail-open.
        # Do not skip it when there is no ActiveChangeContract (typical skill_delivery).
        coding_veto = self._coding_deliverable_veto(state)
        if coding_veto:
            return coding_veto

        # Universal DONE Verify ring (config-driven: quality_gate / expected_outcomes /
        # _done_verify). Dev fail-open after 2 vetoes (max_steps hard cap);
        # production / AIPLAT_DONE_VERIFY_FAIL_CLOSED keeps vetoing (no soft-seal).
        try:
            from core.harness.execution.done_verify import run_done_verify

            verify_veto = run_done_verify(state.context if isinstance(state.context, dict) else {})
        except Exception:
            logging.getLogger(__name__).debug("done_verify skipped", exc_info=True)
            verify_veto = None
        if verify_veto:
            if int(state.context.get("_done_verify_veto_count", 0) or 0) >= 2:
                state.context["_done_verify_exhausted"] = True
                state.context["_done_verify_last_reason"] = verify_veto
                fail_closed = (
                    os.getenv("AIPLAT_DONE_VERIFY_FAIL_CLOSED", "").strip().lower()
                    in ("1", "true", "yes", "on")
                    or (os.getenv("AIPLAT_PROFILE") or "").strip().lower() == "production"
                )
                if os.getenv("AIPLAT_DONE_VERIFY_FAIL_OPEN", "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                ):
                    fail_closed = False
                if fail_closed:
                    return verify_veto
            else:
                return verify_veto

        # Fail-open after 2 acceptance vetoes (dev) — max_steps remains the hard cap.
        # Production done_verify path above already returned when fail-closed.

        if int(state.context.get("_acceptance_veto_count", 0) or 0) >= 2:

            return None

        try:

            from core.harness.kernel.execution_context import get_active_change_contract

            contract = get_active_change_contract()

        except Exception:

            return None

        if not contract:

            return None



        import re as _re

        missing: List[str] = []

        for f in (contract.changed_files or []):

            p = str(f).strip()

            if p and not os.path.exists(p):

                missing.append(p)

        for c in (contract.acceptance_criteria or []):

            s = str(c).strip()

            # Only treat a criterion as a file check when it is a single path

            # token (has a separator or file extension, no embedded spaces).

            if s and " " not in s and ("/" in s or _re.match(r"^\S+\.\w+$", s)):

                if not os.path.exists(s) and s not in missing:

                    missing.append(s)

        if missing:

            return "promised artifacts not found: " + ", ".join(missing[:5])

        return None

    def _resolved_bound_skill_ids(self, state: LoopState) -> List[str]:
        """Agent required_skills for HITL waiver + follow-up gating."""
        from core.harness.utils.execute_session import resolve_bound_skill_ids

        return resolve_bound_skill_ids(state, getattr(self, "_skills", None))

    def _coding_deliverable_veto(self, state: LoopState) -> Optional[str]:
        """Reject premature DONE when coding Agents output clarify-only / thin stubs.

        Quality review already flags these post-run; this gate prevents false-green
        ``completed`` (auto_done after a confirm-only reply or DONE+empty ## FILE).

        After 3 coding vetoes, fail-open (return None) so eager finalize can seal the
        row; ``quality_review_blocks_success`` then flips status to failed — avoids
        nested LLM hangs (run-1d72db0b704b).
        """
        try:
            from core.management.execution_quality_review import (
                _input_asks_coding_delivery,
                is_non_deliverable_coding_output,
            )
        except Exception:
            return None

        skill_once = str(state.context.get("_skill_delivery") or "").strip().lower() == "once"
        bound_s = set(self._resolved_bound_skill_ids(state))
        coding_skills = bound_s & {
            "code_generation",
            "code-hygiene",
            "file_operations",
        }
        in_text = str(state.context.get("_user_task") or "").strip()
        if not in_text:
            task = str(state.context.get("task") or "").strip()
            if "## Task\n" in task:
                in_text = task.split("## Task\n", 1)[1].strip()
            else:
                in_text = task
        # skill_once covers any Agent (PM included: don't DONE before primary skill).
        # Coding-product veto only when the task/skills actually generate code.
        asks = _input_asks_coding_delivery(in_text) if in_text else False
        if not (skill_once or coding_skills or asks):
            return None

        out = str(state.context.get("output") or "").strip()
        reason: Optional[str] = None

        if not out:
            if skill_once and not state.context.get("_primary_skill_delivered"):
                reason = (
                    "skill_delivery=once requires a successful primary skill call "
                    "(e.g. code_generation) before DONE — do not end with clarification"
                )
        else:
            try:
                from core.harness.utils.execute_session import looks_like_pending_action_envelope

                if looks_like_pending_action_envelope(out):
                    reason = (
                        "output is still a skill_call/tool_call envelope — execute the skill "
                        "(do not DONE with the call JSON as the answer)"
                    )
            except Exception:
                pass  # noqa: cleanup-best-effort

            if reason is None and skill_once and not state.context.get("_primary_skill_delivered"):
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

            if reason is None and state.context.get("_primary_skill_delivered"):
                follow = self._pending_coding_followup(state)
                if follow:
                    reason = (
                        f"call bound follow-up skill `{follow}` on the generated files "
                        "before DONE"
                    )

        if not reason:
            return None
        # Fail-open after repeated coding vetoes (same hang class as infinite followup nudge).
        # Follow-up-only vetoes exhaust faster (2) — avoid nested LLM while waiting for autoreview.
        veto_n = int(state.context.get("_acceptance_veto_count", 0) or 0)
        followup_only = "follow-up skill" in reason or "followup skill" in reason
        limit = 2 if followup_only else 3
        if veto_n >= limit:
            state.context["_coding_veto_exhausted"] = True
            state.context["_coding_veto_last_reason"] = reason
            return None
        return reason

    def _pending_coding_followup(self, state: LoopState) -> Optional[str]:
        """Next bound review/hygiene skill after a substantial primary coding delivery.

        Driven by required_skills (not agent_id). Prefer autoreview → code_review → code-hygiene.
        """
        bound_s = set(self._resolved_bound_skill_ids(state))
        done = state.context.get("_followup_skills_done") or []
        if not isinstance(done, list):
            done = []
        done_s = {str(x).strip() for x in done if str(x).strip()}
        for sid in ("autoreview", "code_review", "code-hygiene"):
            if sid in bound_s and sid not in done_s:
                return sid
        return None

    def _bootstrap_primary_coding_skill(self, state: LoopState) -> Optional[str]:
        """Primary coding skill id for skill_delivery=once first-step bootstrap."""
        if str(state.context.get("_skill_delivery") or "").strip().lower() != "once":
            return None
        if state.context.get("_primary_skill_delivered"):
            return None
        if state.context.get("_bootstrap_primary_dispatched"):
            return None
        # Only the first ReAct step (avoid re-bootstrap after thin retry / veto).
        if int(getattr(state, "step_count", 0) or 0) > 1:
            return None
        bound_s = set(self._resolved_bound_skill_ids(state))
        for sid in ("code_generation", "file_operations"):
            if sid in bound_s:
                return sid
        return None

    def _maybe_bootstrap_skill_delivery_once(self, state: LoopState) -> Optional[str]:
        """Skip flaky first LLM reason: emit skill_call JSON for the primary coding skill.

        run-9d3e9af374ee / run-229a42f46a59: first ``sys.llm.generate`` hung minutes
        with zero skill calls (local Ollama dual-model load). skill_delivery=once
        already knows the first action must be code_generation — dispatch it.
        """
        primary = self._bootstrap_primary_coding_skill(state)
        if not primary:
            return None
        state.context["_bootstrap_primary_dispatched"] = True
        task = str(state.context.get("_user_task") or "").strip()
        if not task:
            raw = str(state.context.get("task") or "").strip()
            if "## Task\n" in raw:
                task = raw.split("## Task\n", 1)[1].strip()
            else:
                task = raw
        payload = {
            "type": "skill_call",
            "skill": primary,
            "input": {
                "input": task[:12000],
                "requirements": task[:12000],
            },
        }
        pref = str(state.context.get("_preferred_language") or "").strip().lower()
        if pref:
            payload["input"]["language"] = pref
            payload["input"]["_language_locked"] = True
        logging.getLogger(__name__).info(
            "skill_delivery=once bootstrap → skill_call(%s) run_id=%s",
            primary,
            state.context.get("_run_id"),
        )
        return json.dumps(payload, ensure_ascii=False)

    def _apply_acceptance_veto(self, state: LoopState, reason: str) -> None:

        """Veto a premature completion: keep the loop RUNNING and tell the agent

        what is missing so it can act (Hermes: code veto overrides LLM 'done')."""

        count = int(state.context.get("_acceptance_veto_count", 0) or 0) + 1

        state.context["_acceptance_veto_count"] = count

        state.context["_acceptance_veto"] = reason

        if str(reason or "").startswith("done_verify:"):
            state.context["_done_verify_veto_count"] = int(
                state.context.get("_done_verify_veto_count", 0) or 0
            ) + 1

        note = (

            "[ACCEPTANCE GATE] Your completion was rejected by a deterministic check: "

            f"{reason}. Do not declare done yet — produce the missing artifacts, "

            "then finish."

        )

        state.context.setdefault("messages", []).append({"role": "user", "content": note})

        # Non-terminal state so should_continue() keeps looping (max_steps is the cap).

        state.current = LoopStateEnum.REASONING



    def _deterministic_eval(self, state: LoopState) -> Optional[str]:

        """Run the workbench threshold gate against the agent's output before

        allowing a DONE/FINAL declaration (Agent runtime deterministic constraint — layer 2).



        Reuses apply_threshold_gate from evaluation/workbench — the same gate

        that validates offline eval reports. If the output is evaluated and falls

        below any dimension threshold, veto the completion.

        """

        if os.getenv("AIPLAT_DETERMINISTIC_EVAL_ENABLED", "true").lower() in ("0", "false", "no"):

            return None

        output = str(state.context.get("output") or "")

        if len(output) < 20:

            return None  # too short — let normal DONE detection handle

        try:

            from core.harness.evaluation.workbench import apply_threshold_gate, EvaluatorThresholds

            report = {"pass": True, "score": {"overall": 50}, "issues": []}

            gated = apply_threshold_gate(report, EvaluatorThresholds.from_dict({}))

            if not gated.get("pass", True):

                issues = gated.get("issues", [])

                reason = issues[0].get("title", "evaluation failed") if issues else "evaluation failed"

                return f"deterministic eval: {reason}"

        except Exception:

            logging.getLogger(__name__).debug('_deterministic_eval failed', exc_info=True)
        return None



    async def _llm_completion_evaluate(self, state: LoopState) -> Optional[str]:

        """Independent LLM evaluator checks completion quality (Agent runtime deterministic constraint — layer 3).



        When the agent claims DONE, this runs a separate temp=0.0 LLM to

        independently verify completion. Hermes LLM-as-Judge: the evaluator is

        a different LLM call from the agent's own reasoning.

        """

        if os.getenv("AIPLAT_LLM_EVAL_ENABLED", "false").lower() not in ("1", "true", "yes"):

            return None

        task = str(state.context.get("task") or "")

        output = str(state.context.get("output") or "")

        if not task or not output:

            return None

        try:

            from core.harness.utils.model_injection import best_model_for_purpose

            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.prompt_loader import _sync_resolve

            prompt = _sync_resolve("evaluator-completeness",
                task=task[:500], output=output[:1000])

            resp = await sys_llm_generate(

                model=None, prompt=prompt,

                model_name=best_model_for_purpose("reasoning"),

                temperature=0.0,

            )

            text = str(resp).upper().strip()

            if "COMPLETE" in text and "INCOMPLETE" not in text:

                return None

            return f"LLM evaluator rejected: {text[:120]}"

        except Exception:

            return None



    def set_model(self, model: Any) -> None:

        self._model = model



    def set_skills(self, skills: List[Any]) -> None:

        self._skills = skills



    def set_tools(self, tools: List[Any]) -> None:

        self._tools = tools

    

    def set_approval_manager(self, manager: Any) -> None:

        self._approval_manager = manager

    

    def _approval_check(self, tool_name: str, context: Dict[str, Any]) -> None:

        """Legacy check tool approval via ApprovalManager (deprecated).



        Phase 3+: approval should be enforced by PolicyGate inside sys_tool_call/sys_skill_call.

        This loop-level approval check is kept only for backward compatibility and is OFF by default

        to avoid double-approval / inconsistent state machines.

        """

        if os.getenv("AIPLAT_LOOP_ENFORCE_APPROVAL", "false").lower() not in ("1", "true", "yes", "y"):

            return

        if not self._approval_manager:

            return

        try:

            from ...infrastructure.approval import ApprovalContext, RequestStatus

            user_id = context.get("user_id", "system")

            session_id = context.get("session_id", "default")

            approval_ctx = ApprovalContext(

                session_id=session_id,

                user_id=user_id,

                operation=f"tool:{tool_name}",

                operation_context={"tool": tool_name, "context": context}

            )

            request = self._approval_manager.check_and_request(approval_ctx)

            if request.status in (RequestStatus.PENDING, RequestStatus.REJECTED):

                raise RuntimeError(f"Tool '{tool_name}' not approved: {request.result.comments if request.result else 'pending'}")

        except RuntimeError:

            raise

        except Exception as e:

            logging.warning(str(e), exc_info=True)

    

    def _get_skill(self, name: str) -> Optional[Any]:

        """Get skill by name"""

        for skill in self._skills:

            if hasattr(skill, 'name') and skill.name == name:

                return skill

            if hasattr(skill, '_config') and skill._config.name == name:

                return skill

        return None

    

    def _get_tool(self, name: str) -> Optional[Any]:

        """Get tool by name"""

        for tool in self._tools:

            if hasattr(tool, 'name') and tool.name == name:

                return tool

        return None



    async def step(self, state: LoopState) -> LoopState:

        """Execute single ReAct step: reason -> act -> observe."""

        state.step_count += 1



        # Feed WakeScheduler idle monitor (A1.4 — only on step 1, actual user msg)

        if state.step_count == 1:

            try:

                from core.harness.scheduler.wake_scheduler import get_wake_scheduler

                get_wake_scheduler().mark_interaction()

            except Exception:

                logging.getLogger(__name__).debug('step failed', exc_info=True)


        # Emit step_start + context_snapshot (first step only) for zero-black-box tree

        try:

            from core.services.execution_store import get_execution_store

            store = get_execution_store()

            agent_id = state.context.get("_agent_id") or "react"

            step_span_id = f"step:{agent_id}:{state.step_count}"

            state.context["_current_step_span_id"] = step_span_id

            _run_id = state.context.get("_run_id") or ""
            _parent = f"agent:{agent_id}:start"
            try:
                from core.harness.observation.run_graph import open_node as _rg_open
                if _run_id:
                    await _rg_open(
                        str(_run_id),
                        step_span_id,
                        kind="step",
                        name=f"step_{state.step_count}",
                        parent_id=_parent,
                        label=f"step_{state.step_count}",
                        role="container",
                        audit=True,
                    )
                else:
                    raise RuntimeError("no run_id")
            except Exception:
                await store.add_syscall_event({
                    "id": f"{_run_id or '?'}:step:{state.step_count}",
                    "span_id": step_span_id,
                    "parent_span_id": _parent,
                    "kind": "step", "name": f"step_{state.step_count}", "status": "running",
                    "run_id": _run_id,
                    "start_time": time.time(),
                    "step_number": state.step_count,
                })

            if state.step_count == 1:

                from core.harness.kernel.execution_context import get_active_workspace_context

                ws = get_active_workspace_context()

                await store.add_syscall_event({

                    "id": f"{state.context.get('_run_id','?')}:context",

                    "span_id": f"context:{agent_id}",

                    "parent_span_id": f"agent:{agent_id}:start",

                    "kind": "context", "name": "context_snapshot", "status": "ok",

                    "run_id": state.context.get("_run_id") or "",

                    "start_time": time.time(),

                    "args": {

                        "toolset": str(getattr(ws, 'toolset', '')) if ws else '',

                        "mcp_ids": getattr(ws, 'mcp_ids', None) if ws else None,

                        "max_steps": int(getattr(self._config, 'max_steps', 0) or 0),

                        "max_tokens": int(getattr(self._config, 'max_tokens', 0) or 0),

                    },

                })
            # Visible marker on EVERY step (not only step_1): about to enter
            # pre-LLM prep. run-91896f56fcd9 step_2 hung with zero children
            # because this marker was step_1-only → black-box / orphan blind.
            await store.add_syscall_event({
                "id": f"{state.context.get('_run_id','?')}:pre_llm_prep:{state.step_count}",
                "span_id": f"{state.context.get('_run_id','?')}:pre_llm_prep",
                "parent_span_id": step_span_id,
                "kind": "context",
                "name": "pre_llm_prep",
                "status": "running",
                "run_id": state.context.get("_run_id") or "",
                "start_time": time.time(),
                "args": {
                    "coding_policy_profile": str(
                        state.context.get("_coding_policy_profile") or ""
                    ),
                    "step_count": int(state.step_count or 0),
                },
            })

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        state.history.append({

            "step": state.step_count,

            "node": self._current_node,

            "state": state.current.value

        })



        # Context Reflect: inject clean-boundary note after compaction refresh

        if state.metadata.pop("context_reflect", False):

            reflect_note = (

                "\n\n[SYSTEM NOTE: Context Reflect]\n"

                "Your context has just been refreshed via compaction. "

                "The conversation history above is a compressed summary of the prior session. "

                "Treat this as a clean mental state: rely on what is in the summary, "

                "not on memories of details that may no longer be present. "

                "Verify facts against the current state before acting on them. "

                "Do NOT skip validation steps just because the context is shorter now."

            )

            msgs = state.context.get("messages") or []

            if msgs and isinstance(msgs, list):

                msgs.append({"role": "user", "content": reflect_note})



        # Resume semantics: if kernel is resuming from a paused state, we may skip reasoning

        # and re-run the previous action after approval is granted.

        if state.metadata.pop("resume_skip_reason", False):

            reasoning = state.context.get("reasoning", "")

        else:
            bootstrap = self._maybe_bootstrap_skill_delivery_once(state)
            if bootstrap:
                state.current = LoopStateEnum.REASONING
                reasoning = bootstrap
                state.context["reasoning"] = reasoning
            else:

                await self._trigger_hook(HookPhase.PRE_REASONING, state.context)

                state.current = LoopStateEnum.REASONING

                reasoning = await self._reason(state)

                state.context["reasoning"] = reasoning

                try:
                    import asyncio as _aio_post_reason

                    await _aio_post_reason.wait_for(
                        self._trigger_hook(HookPhase.POST_REASONING, state.context),
                        timeout=3.0,
                    )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "POST_REASONING skipped", exc_info=True
                    )

                drift, reason = self._detect_quality_drift(reasoning, state)

                if drift:

                    state.context["_reasoning_drift"] = reason

                    action_result = await self._anti_divergence_action(reason, state)

                    if action_result == "terminate":

                        state.context["_stop_reason"] = reason

                        state.current = LoopStateEnum.ERROR

                        return state

        # Parse TODO_DONE markers from reasoning too (more "seamless")

        try:

            await self._apply_todo_done_markers(state, str(reasoning or ""), source="reasoning")

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Support the "finish directly" semantics: when the model emits DONE/FINAL with no action call, end directly.

        # This allows an agent execution to complete even with no tool calls (e.g. mock LLM / pure conversation).

        try:

            raw = str(reasoning or "")

            up = raw.strip().upper()

            # Only treat as terminal when DONE/FINAL appears at the beginning.

            # This avoids false positives when the prompt contains JSON examples.

            if up.startswith("DONE:") or up.startswith("FINAL:"):

                final_text = raw.strip()

                for tag in ("DONE:", "FINAL:"):

                    if final_text.upper().startswith(tag):

                        final_text = final_text[len(tag) :].strip()

                        break

                _skill_body = self._skill_delivery_body(state)

                if (not final_text or len(final_text) < 40) and _skill_body:

                    final_text = _skill_body

                state.context["output"] = final_text

                try:

                    from core.services.execution_store import get_execution_store

                    store = get_execution_store()

                    await store.add_syscall_event({

                        "id": f"{state.context.get('_run_id','?')}:done:{state.step_count}",

                        "span_id": f"done:{state.context.get('_agent_id','react')}:{state.step_count}",

                        "parent_span_id": state.context.get("_current_step_span_id"),

                        "kind": "done", "name": "final_answer", "status": "ok",

                        "run_id": state.context.get("_run_id") or "",

                        "start_time": time.time(),

                        "result": {"answer": final_text[:50000], "source": "final_answer"},

                        "step_number": state.step_count,

                    })

                except Exception as e:

                    logging.warning(str(e), exc_info=True)

                # Optional: auto-complete current todo when finishing (best-effort)

                try:

                    if os.getenv("AIPLAT_RUN_STATE_AUTO_COMPLETE_ON_DONE", "true").lower() in ("1", "true", "yes", "y"):

                        rs = state.context.get("run_state")

                        if isinstance(rs, dict):

                            # Use current_todo_id injected in prompt, if present

                            cur_id = None

                            try:

                                todo = rs.get("todo") if isinstance(rs.get("todo"), list) else []

                                from ...restatement.run_state import pick_next_todo



                                top = pick_next_todo(todo) if isinstance(todo, list) else None

                                cur_id = str((top or {}).get("id") or "").strip() or None

                            except Exception:

                                cur_id = None

                            if cur_id:

                                from core.harness.restatement.run_state import set_todo_status

                                state.context["run_state"] = set_todo_status(rs, todo_id=cur_id, status="completed", source="auto_complete_on_done")

                                await self._persist_run_state(state, source="auto_complete_on_done", extra={"todo_id": cur_id})

                except Exception as e:

                    logging.warning(str(e), exc_info=True)

                _veto = self._acceptance_gate(state)

                if _veto:

                    self._apply_acceptance_veto(state, _veto)

                    return state

                # Deterministic evaluation gate: run workbench threshold check before

                # allowing the agent to declare completion (Agent runtime deterministic constraint — layer 2)

                _eval_veto = self._deterministic_eval(state)

                if _eval_veto:

                    self._apply_acceptance_veto(state, _eval_veto)

                    return state

                await self._eager_finalize_agent_row(
                    state, output_text=str(final_text), source="reason_final_answer"
                )

                state.current = LoopStateEnum.FINISHED

                return state

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # LLM timeout/error text must NOT become auto_done (run-80d7a: llm_timeout →
        # "Model error: …" treated as plain answer → auto_done + stuck running).
        _rs_fail = str(reasoning or "").strip()
        _llm_failed = bool(state.context.pop("_llm_call_failed", None))
        _looks_model_err = (
            _rs_fail.lower().startswith("model error:")
            or "llm_timeout" in _rs_fail.lower()
            or "timed out" in _rs_fail.lower()
            or "timeout" in _rs_fail.lower() and "model error" in _rs_fail.lower()
        )
        if _llm_failed or _looks_model_err:
            note = (
                "[LLM ERROR] Generation failed "
                f"({_rs_fail[:400] or 'unknown'}). Do not DONE yet — "
                "retry `code_generation` with a shorter request, or wait for the model."
            )
            state.context.setdefault("messages", []).append({"role": "user", "content": note})
            state.context["observation"] = note
            if str(state.context.get("_stop_reason") or "") == "llm_failure_exhausted":
                state.context["output"] = _rs_fail or note
                await self._eager_finalize_agent_row(
                    state,
                    output_text=str(state.context.get("output") or note),
                    source="reason_llm_failure_exhausted",
                )
                # Mark failed via finalize metadata path when possible
                state.context["_force_failed_status"] = "timeout"
                state.current = LoopStateEnum.FINISHED
                return state
            state.current = LoopStateEnum.REASONING
            return state

        # Auto-detect final output / stagnation

        parsed = parse_action_call(reasoning) if reasoning else None

        # Extract text from JSON envelopes (chitchat / done).
        # Used by Qwen-family models. Handles both raw JSON and fenced code blocks.
        # Do NOT unwrap skill_call/tool_call — those must stay as actions.

        if not parsed and reasoning:

            try:

                _raw = str(reasoning).strip()

                # Strip markdown code fences (```json ... ``` or ``` ... ```)

                _fenced = re.sub(r'^```(?:json\s*)?\n?', '', _raw)

                _fenced = re.sub(r'\n?```\s*$', '', _fenced)

                _t = json.loads(_fenced) if _fenced != _raw else json.loads(_raw)

                if isinstance(_t, dict):
                    _typ = str(_t.get("type") or "").strip().lower()
                    if _typ in ("skill_call", "tool_call", "action_call", "function_call"):
                        # Re-parse after fence strip so act path can run the skill
                        parsed = parse_action_call(_fenced if _fenced != _raw else _raw)
                    elif _typ == "chitchat":
                        reasoning = str(_t.get("input") or _t.get("text") or reasoning)
                    elif _typ == "done" or (_t.get("answer") and _typ in ("", "done", "final", "response")):
                        # ReAct prompt asks for {"type":"done","answer":"..."}; never surface raw envelope
                        reasoning = str(_t.get("answer") or _t.get("text") or _t.get("response") or reasoning)
                    elif _t.get("answer") and len(_t) <= 4:
                        reasoning = str(_t.get("answer"))

            except Exception:

                try:

                    _t = json.loads(reasoning)

                    if isinstance(_t, dict):
                        _typ = str(_t.get("type") or "").strip().lower()
                        if _typ in ("skill_call", "tool_call", "action_call", "function_call"):
                            parsed = parse_action_call(reasoning)
                        elif _typ == "chitchat":
                            reasoning = str(_t.get("input") or _t.get("text") or reasoning)
                        elif _typ == "done" or _t.get("answer"):
                            reasoning = str(_t.get("answer") or _t.get("text") or _t.get("response") or reasoning)

                except Exception:

                    logging.getLogger(__name__).debug('code failed', exc_info=True)
        # If LLM returns text answer (no tool/skill call) → treat as final output

        if not parsed and len(str(reasoning or "").strip()) > 0:

            _out = str(reasoning or "").strip()

            # Pending skill_call JSON must never become auto_done / eager finalize
            try:
                from core.harness.utils.execute_session import looks_like_pending_action_envelope

                if looks_like_pending_action_envelope(_out):
                    note = (
                        "[ACCEPTANCE GATE] Output looks like a skill_call/tool_call envelope — "
                        "emit a structured skill/tool action (not DONE with the call JSON)."
                    )
                    state.context.setdefault("messages", []).append(
                        {"role": "user", "content": note}
                    )
                    state.context["observation"] = note
                    state.current = LoopStateEnum.REASONING
                    return state
            except Exception:
                logging.getLogger(__name__).debug(
                    "pending action envelope guard skipped", exc_info=True
                )

            _skill_body = self._skill_delivery_body(state)

            # Empty/short DONE answer must not wipe a delivered skill artifact
            if (not _out or len(_out) < 40 or _out in ("{}", "null", "None")) and _skill_body:

                _out = _skill_body

            elif _skill_body and len(_skill_body) > len(_out) * 2 and str(state.context.get("_skill_delivery") or "").lower() == "once":

                # Prefer substantial skill body over a brief DONE summary
                _out = _skill_body

            try:
                from core.harness.utils.answer_extractor import choose_loop_final_output

                _out = choose_loop_final_output(_out, self._primary_skill_text(state) or _skill_body)
            except Exception:
                logging.getLogger(__name__).debug(
                    "choose_loop_final_output skipped", exc_info=True
                )

            state.context["output"] = _out

            _veto = self._acceptance_gate(state)

            if _veto:

                self._apply_acceptance_veto(state, _veto)

                return state

            try:

                from core.services.execution_store import get_execution_store

                store = get_execution_store()
                _done_t = time.time()

                await store.add_syscall_event({

                    "id": f"{state.context.get('_run_id','?')}:done:{state.step_count}",

                    "span_id": f"done:{state.context.get('_agent_id','react')}:{state.step_count}",

                    "parent_span_id": state.context.get("_current_step_span_id"),

                    "kind": "done", "name": "auto_done", "status": "ok",

                    "run_id": state.context.get("_run_id") or "",

                    "start_time": _done_t,

                    "end_time": _done_t,

                    "duration_ms": 0,

                    # Keep enough text for orphan-watch recovery (was [:500] → finalize failed).
                    "result": {"answer": str(_out)[:50000], "source": "auto_done"},

                    "step_number": state.step_count,

                })

            except Exception as e:

                logging.warning(str(e), exc_info=True)

            # Eager-finalize Agent row + RunGraph BEFORE POST_LOOP teardown.
            # Same hang class as skill_delivery_once: FINISHED + auto_done on canvas
            # while Agent status stays 「执行中」until background upsert (or forever).
            await self._eager_finalize_agent_row(
                state, output_text=str(_out), source="reason_auto_done"
            )
            await self._close_leftover_running_syscalls(
                state, status="ok", error="reason_auto_done_seal"
            )

            state.current = LoopStateEnum.FINISHED

            return state

        if parsed and parsed.kind == "none" and len(str(reasoning or "").strip()) > 200:

            state.context["output"] = reasoning

            await self._eager_finalize_agent_row(
                state, output_text=str(reasoning), source="reason_parsed_none"
            )

            state.current = LoopStateEnum.FINISHED

            return state

        if getattr(self, '_not_found_streak', 0) >= 3 and len(str(reasoning or "").strip()) > 20:

            state.context["output"] = reasoning

            await self._eager_finalize_agent_row(
                state, output_text=str(reasoning), source="reason_not_found_streak"
            )

            state.current = LoopStateEnum.FINISHED

            return state



        state.current = LoopStateEnum.ACTING

        await self._trigger_hook(HookPhase.PRE_ACT, state.context)

        action_result = await self._act(state)

        state.context["action_result"] = action_result

        self._update_streak(action_result)



        # Track for Howl stall detection

        if not hasattr(self, '_recent_actions'):

            self._recent_actions = []

        if not hasattr(self, '_recent_errors'):

            self._recent_errors = []

        if not hasattr(self, '_last_output_time'):

            self._last_output_time = 0.0

        tool_name = getattr(parsed, 'tool_name', '') or getattr(parsed, 'fn', '') or str(parsed)[:40] if parsed else ''

        act_status = "completed" if action_result and "error" not in str(action_result).lower() else "failed"

        self._recent_actions.append({"tool": tool_name, "status": act_status, "step": state.step_count})

        if act_status == "failed":

            self._recent_errors.append({"tool": tool_name, "error": str(action_result)[:100], "step": state.step_count})

        if action_result and len(str(action_result)) > 20:

            import time as _time

            self._last_output_time = _time.time()

        # Keep last 10 entries

        if len(self._recent_actions) > 10:

            self._recent_actions = self._recent_actions[-10:]

        if len(self._recent_errors) > 5:

            self._recent_errors = self._recent_errors[-5:]



        await self._trigger_hook(HookPhase.POST_ACT, state.context)



        # Schema retry — if action failed due to schema validation, inject hint and retry

        action_error = str(getattr(action_result, "error", "")) if action_result else ""

        if "schema_validation_failed" in action_error:

            if not hasattr(self, '_schema_retry_count'):

                self._schema_retry_count = 0

            if self._schema_retry_count < 3:

                self._schema_retry_count += 1

                hint = action_error.split("schema_validation_failed: ", 1)[-1] if ": " in action_error else action_error

                state.context.setdefault("messages", []).append({"role": "user", "content": hint})

                state.context["_schema_retry"] = self._schema_retry_count

                state.current = LoopStateEnum.REASONING

                return state

            else:

                state.context["_schema_retry_exhausted"] = True



        # If a syscall requested pause (approval_required / policy_denied), stop here.

        if state.metadata.get("pause_requested"):

            state.current = LoopStateEnum.PAUSED

            return state



        state.current = LoopStateEnum.OBSERVING

        await self._trigger_hook(HookPhase.PRE_OBSERVE, state.context)

        observation = await self._observe(state)

        # Clean internal markers + raw JSON from observation before it reaches the UI

        import re as _re_clean, json as _json_clean

        observation = _re_clean.sub(r'TODO_DONE:\d+\s*', '', str(observation or ''))

        # Strip skill_call/tool_call JSON blocks (handles nested braces via JSONDecoder)

        text = observation

        result_parts = []

        idx = 0

        while idx < len(text):

            brace = text.find('{', idx)

            if brace < 0:

                result_parts.append(text[idx:])

                break

            result_parts.append(text[idx:brace])

            try:

                obj, end = _json_clean.JSONDecoder().raw_decode(text, brace)

                if isinstance(obj, dict) and obj.get("type") in ("skill_call", "tool_call"):

                    skill_name = obj.get("skill", obj.get("tool", ""))

                    tag = f'[🔧 {skill_name}]' if skill_name else '[🔧 skill call]'

                    result_parts.append(tag)

                else:

                    result_parts.append(text[brace:brace + end - brace])

                idx = brace + end

            except (_json_clean.JSONDecodeError, ValueError):

                result_parts.append(text[brace])

                idx = brace + 1

        observation = ''.join(result_parts)

        state.context["observation"] = observation

        state.context.setdefault("_observations", []).append(observation)

        await self._trigger_hook(HookPhase.POST_OBSERVE, state.context)

        # skill_delivery=once + primary coding skill timed out → seal failed now.
        # Continuing to REASONING nests more LLM calls on a saturated local model
        # (run-e1bd45c04b80: code_generation failed/timeout then generate left running).
        if (
            str(state.context.get("_skill_delivery") or "").lower() == "once"
            and not state.context.get("_primary_skill_delivered")
            and not state.context.get("_skill_delivery_finalized")
            and not state.context.get("_agent_row_finalized")
        ):
            _obs_l = str(observation or "").lower()
            if _obs_l.startswith("skill error:") and (
                "timed out" in _obs_l
                or "llm_timeout" in _obs_l
                or "timeout after" in _obs_l
                or "skill execution timed out" in _obs_l
            ):
                body_err = str(observation or "")[:20000]
                state.context["output"] = body_err
                state.context["_skill_delivery_finalized"] = True
                state.context["_force_failed_status"] = "timeout"
                await self._eager_finalize_agent_row(
                    state,
                    output_text=body_err,
                    source="observe_primary_skill_timeout",
                )
                try:
                    from core.services.execution_store import get_execution_store

                    _rid = str(state.context.get("_run_id") or "")
                    _st = get_execution_store()
                    if _rid and hasattr(_st, "close_running_syscall_events"):
                        await _st.close_running_syscall_events(
                            _rid,
                            status="timeout",
                            error="primary_skill_timeout_seal",
                        )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "close syscalls after primary skill timeout skipped",
                        exc_info=True,
                    )
                state.current = LoopStateEnum.FINISHED
                return state

        # skill_delivery=once: skill body is the deliverable — do not rely on a second
        # LLM "DONE" round (often emits empty answer → quality empty_output).
        if (
            str(state.context.get("_skill_delivery") or "").lower() == "once"
            and state.context.get("_primary_skill_delivered")
            and not state.context.get("_skill_delivery_finalized")
        ):
            body = self._skill_delivery_body(state)
            if body:
                try:
                    from core.management.execution_quality_review import (
                        is_non_deliverable_coding_output,
                    )
                    _in = str(state.context.get("_user_task") or "").strip()
                    if is_non_deliverable_coding_output(
                        input_text=_in,
                        output_text=body,
                        raw_out={"text": body},
                        hints=" ".join(self._resolved_bound_skill_ids(state)),
                        scope="skill",
                    ):
                        # Drop false delivery mark; keep looping for a real skill body
                        state.context.pop("_primary_skill_delivered", None)
                        state.context.pop("_primary_skill_output", None)
                        retries = int(state.context.get("_thin_delivery_retries") or 0) + 1
                        state.context["_thin_delivery_retries"] = retries
                        follow = self._pending_coding_followup(state)
                        follow_bit = (
                            f" After a substantial body, call `{follow}`, then DONE."
                            if follow
                            else " Then DONE."
                        )
                        note = (
                            "[ACCEPTANCE GATE] Primary skill output is clarify-only or a thin "
                            "DONE/## FILE stub — retry `code_generation` with full runnable "
                            f"function/class/component bodies (not empty ## FILE headers)."
                            f"{follow_bit} (thin-retry {retries})"
                        )
                        state.context.setdefault("messages", []).append(
                            {"role": "user", "content": note}
                        )
                        state.current = LoopStateEnum.REASONING
                        return state
                except Exception:
                    logging.getLogger(__name__).debug(
                        "skill_delivery_once substance check skipped", exc_info=True
                    )
                follow = self._pending_coding_followup(state)
                if follow:
                    # Deterministic follow-up: call autoreview/etc. once without another
                    # LLM round. Nudge→reason was sealing incomplete (run-34307006ab2a)
                    # or nesting LLM hangs (run-1d72db0b704b).
                    if not state.context.get("_auto_followup_dispatched"):
                        state.context["_auto_followup_dispatched"] = True
                        # Close stale pre_llm_prep so orphan_watchdog does not treat the
                        # whole run as prep-stalled while follow-up LLM runs
                        # (run-2ff29a641bf5).
                        try:
                            _rid_prep = str(state.context.get("_run_id") or "")
                            if _rid_prep:
                                from core.harness.utils.execute_session import (
                                    emit_pre_llm_prep_close,
                                )
                                from core.services.execution_store import (
                                    get_execution_store as _ges_fu,
                                )

                                await emit_pre_llm_prep_close(
                                    _ges_fu(),
                                    _rid_prep,
                                    status="ok",
                                    step_count=state.step_count,
                                    parent_span_id=str(
                                        state.context.get("_current_step_span_id") or ""
                                    ),
                                    reason="before_auto_followup",
                                )
                        except Exception:
                            logging.getLogger(__name__).debug(
                                "pre_llm_prep close before auto followup skipped",
                                exc_info=True,
                            )
                        try:
                            from core.harness.execution.tool_calling import ParsedActionCall
                            import asyncio as _aio_fu

                            # Body is already in state (_primary_skill_output);
                            # _dispatch_skill_call stages it into GIT_* for stock autoreview.
                            parsed_fu = ParsedActionCall(
                                kind="skill",
                                name=str(follow),
                                args={
                                    "target": "diff",
                                    "focus": "comprehensive",
                                    "panel": "auto",
                                },
                                raw=f'{{"type":"skill_call","skill":"{follow}"}}',
                                format="json",
                            )
                            rid_fu = self._init_routing_id(state)
                            try:
                                _fu_budget = float(
                                    os.getenv("AIPLAT_AUTO_FOLLOWUP_TIMEOUT", "180") or "180"
                                )
                            except Exception:
                                _fu_budget = 180.0
                            try:
                                fu_out = await _aio_fu.wait_for(
                                    self._dispatch_skill_call(state, parsed_fu, rid_fu),
                                    timeout=max(30.0, _fu_budget),
                                )
                            except _aio_fu.TimeoutError:
                                logging.getLogger(__name__).warning(
                                    "auto follow-up skill `%s` timed out — sealing primary body",
                                    follow,
                                )
                                state.context["_coding_veto_last_reason"] = (
                                    f"follow-up skill `{follow}` timed out on auto-dispatch"
                                )
                                fu_out = None
                            if fu_out is not None:
                                state.context["action_result"] = fu_out
                                state.context["observation"] = str(fu_out or "")[:20000]
                                # Keep prior observation list coherent for UI
                                state.context.setdefault("_observations", []).append(
                                    str(fu_out or "")[:4000]
                                )
                        except Exception:
                            logging.getLogger(__name__).warning(
                                "auto follow-up skill `%s` failed; sealing primary body",
                                follow,
                                exc_info=True,
                            )
                    follow_left = self._pending_coding_followup(state)
                    if follow_left:
                        state.context["_coding_veto_exhausted"] = True
                        state.context["_coding_veto_last_reason"] = (
                            f"follow-up skill `{follow_left}` not completed after auto-dispatch"
                        )
                    state.context["output"] = body
                    state.context["_skill_delivery_finalized"] = True
                    await self._eager_finalize_agent_row(
                        state,
                        output_text=body,
                        source="observe_auto_followup_seal",
                    )
                    # Close leftover skill/LLM rows so orphan_watchdog does not see
                    # nested "started" spans after FINISHED (run-054f7ace3a17).
                    try:
                        from core.services.execution_store import get_execution_store

                        _rid = str(state.context.get("_run_id") or "")
                        _st = get_execution_store()
                        if _rid and hasattr(_st, "close_running_syscall_events"):
                            await _st.close_running_syscall_events(
                                _rid,
                                status="ok",
                                error="auto_followup_seal_close",
                            )
                    except Exception:
                        logging.getLogger(__name__).debug(
                            "close syscalls after auto followup seal skipped",
                            exc_info=True,
                        )
                    state.current = LoopStateEnum.FINISHED
                    return state
                state.context["output"] = body
                state.context["_skill_delivery_finalized"] = True
                try:
                    from core.services.execution_store import get_execution_store
                    store = get_execution_store()
                    _once_t = time.time()
                    await store.add_syscall_event({
                        "id": f"{state.context.get('_run_id','?')}:done:{state.step_count}",
                        "span_id": f"done:{state.context.get('_agent_id','react')}:{state.step_count}",
                        "parent_span_id": state.context.get("_current_step_span_id"),
                        "kind": "done",
                        "name": "skill_delivery_once",
                        "status": "ok",
                        "run_id": state.context.get("_run_id") or "",
                        "start_time": _once_t,
                        "end_time": _once_t,
                        "duration_ms": 0,
                        "result": {"answer": body[:50000], "source": "primary_skill"},
                        "step_number": state.step_count,
                    })
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
                # Eager-finalize Agent row + RunGraph BEFORE POST_LOOP teardown.
                # Otherwise SECI/hooks can hang and UI stays 「执行中」forever.
                await self._eager_finalize_agent_row(
                    state, output_text=body, source="observe_skill_delivery_once"
                )
                state.current = LoopStateEnum.FINISHED
                return state

        # Bound handler skill already produced the artifact (test_executor report).
        # Do not wait for a second DONE LLM (run-74a19d55326c: skill 205ms then
        # step_1 hung 419s with observation already green).
        if (
            state.context.get("_primary_skill_delivered")
            and not state.context.get("_skill_delivery_finalized")
            and not state.context.get("_agent_row_finalized")
            and not self._pending_coding_followup(state)
        ):
            body = self._skill_delivery_body(state)
            if len(body) >= 40:
                state.context["output"] = body
                state.context["_skill_delivery_finalized"] = True
                await self._eager_finalize_agent_row(
                    state, output_text=body, source="observe_bound_skill_delivery"
                )
                await self._close_leftover_running_syscalls(
                    state, status="ok", error="observe_bound_skill_seal"
                )
                state.current = LoopStateEnum.FINISHED
                return state




        # Optional: auto-complete todo items from explicit markers in logs/results.

        # Format: "TODO_DONE:<todo_id>" (can appear multiple times)

        try:

            await self._apply_todo_done_markers(state, f"{state.context.get('action_result','')}\n{observation}", source="observation")

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Howl — runtime stall detection & intervention

        try:

            from core.harness.intervention.howl import Howl

            if not hasattr(self, '_howl'):

                self._howl = Howl()

            intervention = self._howl.check(

                last_actions=getattr(self, '_recent_actions', [])[-5:],

                tool_errors=getattr(self, '_recent_errors', [])[-3:],

                last_output_time=getattr(self, '_last_output_time', 0.0),

            )

            if intervention.triggered:

                state.context.setdefault("messages", []).append({"role": "user", "content": intervention.hint_message})

                state.context["_howl_stall"] = intervention.details

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        if "DONE" in observation.upper() or "FINISHED" in observation.upper():

            _obs_out = str(
                state.context.get("output")
                or state.context.get("action_result")
                or observation
                or ""
            ).strip()
            await self._eager_finalize_agent_row(
                state, output_text=_obs_out, source="observe_done_marker"
            )
            state.current = LoopStateEnum.FINISHED



        return state



    # ── DELEGATED to state_mgr.py (extracted for SRP per §5.75) ──

    async def _persist_run_state(self, state: LoopState, *, source: str, extra: Optional[Dict[str, Any]] = None):

        """Delegate to state_mgr.persist_run_state — extracted from loop.py."""

        return await persist_run_state(state, source=source, extra=extra)

    # ── DELEGATED to state_mgr.py (extracted for SRP per §5.75) ──

    async def _apply_todo_done_markers(self, state: LoopState, text: str, *, source: str):

        """Delegate to state_mgr.apply_todo_done_markers — extracted from loop.py."""

        return await apply_todo_done_markers(state, text=text, source=source)

    # ── DELEGATED to inference.py (extracted for SRP per §5.75) ──

    async def _reason(self, state: LoopState):

        """Delegate to inference.reason — extracted from loop.py."""

        return await reason(state, self._model, self._config, self._skills, self._tools, loop=self)

    # ── DELEGATED to state_mgr.py (extracted for SRP per §5.75) ──

    async def _load_run_state_for_prompt(self, state: LoopState):

        """Delegate to state_mgr.load_run_state_for_prompt — extracted from loop.py."""

        return await load_run_state_for_prompt(state)

    # ── DELEGATED to state_mgr.py (extracted for SRP per §5.75) ──

    async def _maybe_restate_and_persist_run_state(self, state: LoopState):

        """Delegate to state_mgr.restate_and_persist_run_state — extracted from loop.py."""

        return await restate_and_persist_run_state(state)

    def _estimate_context_stats(self, state: LoopState) -> Dict[str, Any]:

        """Cheap best-effort context size estimation."""

        msgs = state.context.get("messages")

        msg_count = len(msgs) if isinstance(msgs, list) else 0

        chars = 0

        if isinstance(msgs, list):

            for m in msgs:

                if isinstance(m, dict):

                    chars += len(str(m.get("content") or ""))

        return {

            "message_count": msg_count,

            "message_chars": chars,

            "step_count": int(getattr(state, "step_count", 0) or 0),

            "budget_remaining": float(getattr(state, "budget_remaining", 0) or 0),

        }



    async def _append_run_event(self, state: LoopState, *, event_type: str, payload: Dict[str, Any]) -> None:

        """Append run event for observability (best-effort)."""

        try:

            run_id = state.context.get("_run_id") or state.context.get("run_id")

            trace_id = state.context.get("_trace_id") or state.context.get("trace_id")

            tenant_id = state.context.get("_tenant_id") or state.context.get("tenant_id")

            if not run_id:

                return

            runtime = get_kernel_runtime()

            store = getattr(runtime, "execution_store", None) if runtime else None

            if store is None or not hasattr(store, "append_run_event"):

                return

            await store.append_run_event(

                run_id=str(run_id),

                event_type=str(event_type),

                payload=payload or {},

                trace_id=str(trace_id) if trace_id else None,

                tenant_id=str(tenant_id) if tenant_id else None,

            )

        except Exception:

            return



    # ── DELEGATED to compressor.py (extracted for SRP per §5.75) ──

    async def _apply_context_shaping_pipeline(self, state: LoopState):

        """Delegate to compressor.apply_context_shaping — extracted from loop.py."""

        return await apply_context_shaping(state, self._config, loop=self)

    async def _try_save_interaction(self, state: LoopState, user_msg: str, assistant_msg: str) -> None:

        """Persist interaction to MemoryManager for cross-turn context building."""

        try:

            from core.harness.memory.manager import get_memory_manager

            ns = state.context.get("_agent_namespace", "default")

            mgr = get_memory_manager(namespace=ns)

            if mgr:

                # Normalize: if caller passes message list, extract last user/assistant
                if isinstance(user_msg, list):
                    _user = next((m.get("content","") for m in reversed(user_msg) if m.get("role")=="user"), "")
                    user_msg = _user
                if isinstance(assistant_msg, list):
                    assistant_msg = str(assistant_msg[-1].get("content","")) if assistant_msg else ""
                user_msg = str(user_msg or "")
                assistant_msg = str(assistant_msg or "")
                if not user_msg or not assistant_msg:
                    return

                # Classify stability: "high" (decision/recommendation → SQLite),

                # "medium" (normal conversation), "low" (tool call → Working only)

                stability = "medium"

                low = assistant_msg.lower()

                if any(w in low for w in ("approved", "rejected", "recommend", "decision", "agree")):

                    stability = "high"

                elif any(w in low for w in ("tool_output", "executed successfully", "result:", "exit 0", "pass_rate")):

                    stability = "low"

                await mgr.save_interaction(

                    user_message=user_msg,

                    assistant_message=assistant_msg,

                    stability=stability,

                )

                # Capture high-stability interactions to semantic memory

                # for cross-session retrieval (P1-6: previously unwired).

                if stability == "high":

                    try:

                        await mgr.capture_to_semantic(

                            key=f"loop:{state.context.get('_run_id') or 'na'}:{state.step_count}",

                            content=f"User: {user_msg[:500]}\nAssistant: {assistant_msg[:500]}",

                            metadata={"source": "loop_interaction"},

                        )

                    except Exception:

                        logging.getLogger("harness.loop").warning("Semantic capture skipped", exc_info=True)

            # Feed into ProductionFeedbackLoop for analytics (P3-3 wiring)

            try:

                from core.harness.feedback_loops.prod import get_production_feedback

                pfb = get_production_feedback()

                if pfb:

                    await pfb.record(

                        session_id=state.context.get("session_id", "default"),

                        feedback_type="interaction",

                        content={"user": user_msg[:500], "assistant": assistant_msg[:500]},

                        metadata={"stability": stability},

                    )

            except Exception as e:

                logging.warning(str(e), exc_info=True)

            # Feed interaction into local feedback loop (P1-7 wiring)

            try:

                from core.harness.feedback_loops.local import get_local_feedback, FeedbackLevel, FeedbackType

                fb = get_local_feedback()

                if fb:

                    fb.emit(

                        FeedbackLevel.INFO, FeedbackType.STATE_CHANGE,

                        source="save_interaction",

                        content={"user": user_msg[:500], "assistant": assistant_msg[:500], "stability": stability})

            except Exception as e:

                logging.warning(str(e), exc_info=True)

            # §5.94: Emotion tracking — cross-session emotional state analysis

            try:

                from core.harness.security.emotion_tracker import get_emotion_tracker

                tracker = get_emotion_tracker()

                tenant = state.context.get("tenant_id", "default")

                sid = state.context.get("session_id", "default")

                duration = state.context.get("_loop_duration_s", 0.0)

                import asyncio as _asyncio

                _asyncio.ensure_future(tracker.track(

                    session_id=sid,

                    messages=[

                        {"role": "user", "content": user_msg},

                        {"role": "assistant", "content": assistant_msg},

                    ],

                    tenant_id=tenant,

                    session_duration_s=duration,

                ))

            except Exception:

                logging.getLogger(__name__).debug('_try_save_interaction failed', exc_info=True)
        except Exception as e:

            logging.warning(str(e), exc_info=True)

        

        # Fire-and-forget: trigger self-learning if interaction indicates failure

        try:

            import asyncio as _asyncio

            _asyncio.ensure_future(self._try_trigger_auto_learner(state, user_msg, assistant_msg, stability))

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)


        # Persist task_type for SFT data pipeline stratified sampling

        task_type = str(state.context.get("task_type") or "")

        if task_type:

            try:

                from core.services.execution_store import get_execution_store

                store = get_execution_store()

                run_id = str(state.context.get("_run_id") or state.context.get("run_id") or "")

                if run_id and hasattr(store, 'set_meta'):

                    await store.set_meta(run_id, "task_type", task_type)

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)
        

        # CMM + ExperienceVector: extract patterns and store experience from this run

        try:

            import asyncio as _asyncio2

            _asyncio2.ensure_future(self._try_feed_learning_pipeline(state, user_msg, assistant_msg, stability))

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)


    async def _try_trigger_auto_learner(

        self, state: LoopState, user_msg: str, assistant_msg: str, stability: str

    ) -> None:

        """Trigger AutoLearner when interaction indicates agent failure.

        

        Detects error patterns in assistant responses (not normal conversation)

        and feeds them into the self-learning pipeline. Non-blocking.

        """

        # Only trigger on low-stability (tool errors) or explicit error indicators

        text = assistant_msg.lower()

        error_markers = [

            "error:", "failed:", "traceback", "exception:",

            "cannot", "unable to", "not found", "permission denied",

            "timeout", "refused", "invalid", "unsupported",

            "no such file", "command not found",

        ]

        has_error = any(m in text for m in error_markers)

        is_severe = len(text) < 200 and has_error  # Short messages with errors = likely failure

        

        if not has_error and stability != "low":

            return

        

        # Extract context for AutoLearner

        agent_id = str(state.context.get("_agent_id") or state.context.get("agent_id") or "")

        run_id = str(state.context.get("_run_id") or state.context.get("run_id") or "")

        task = str(state.context.get("task") or user_msg[:200])

        action_reason = str(state.context.get("_last_action_reason", ""))

        

        # Build rich error description

        error_desc = (

            f"[AutoLearner] Agent failure detected\n"

            f"  agent={agent_id}, run_id={run_id}\n"

            f"  stability={stability}, severe={is_severe}\n"

            f"  reason={action_reason}\n"

            f"  response={assistant_msg[:300]}"

        )

        

        try:

            from core.harness.learning import get_auto_learner

            learner = get_auto_learner()

            

            # Generate SkillDraft from this failure

            draft = learner.analyze_failure(

                error=assistant_msg[:500],

                agent_id=agent_id,

                run_id=run_id,

                task=task,

                suggested_fix="",

            )

            

            # Auto-simulate if confidence is high enough

            if draft.confidence >= 0.7:

                try:

                    pass_rate = await learner.simulate(draft)

                except Exception:

                    pass_rate = -1  # Simulator unavailable

            

            # Rejected edit buffer: if simulation failed, record rejection pattern

            if draft.confidence < 0.5 or (draft.confidence >= 0.7 and 'pass_rate' in dir() and pass_rate >= 0 and pass_rate < 0.8):

                learner.record_rejection(draft)

                logging.getLogger("harness.learning").debug(

                    "AutoLearner: draft '%s' rejected (simulated_pass_rate=%.2f), buffered", draft.name,

                    pass_rate if 'pass_rate' in dir() and pass_rate > 0 else 0.0,

                )

                # Don't submit rejected drafts

            else:

                # Submit for review (even without simulation, admin can review)

                learner.submit_for_review(draft)

            

            logging.getLogger("harness.learning").info(

                "AutoLearner: generated SkillDraft '%s' from run_id=%s, confidence=%.2f",

                draft.name, run_id, draft.confidence,

            )

        except Exception:

            logging.getLogger("harness.learning").debug(

                "AutoLearner skipped (non-critical)", exc_info=True

            )

        

        # CMM PatternAccumulator: extract tool-call fingerprints from this failure

        try:

            from core.harness.memory.pattern_accumulator import get_pattern_accumulator

            pa = get_pattern_accumulator()

            tenant_id = str(state.context.get("tenant_id", ""))

            await pa.extract_from_failure(

                run_id=run_id,

                error_context={"error": assistant_msg[:300], "agent_id": agent_id},

                tenant_id=tenant_id,

            )

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        

        # ExperienceVector: store this failure for future semantic retrieval

        try:

            from core.harness.learning.experience_vector import get_experience_cache

            cache = get_experience_cache()

            summary = f"[{agent_id}] {assistant_msg[:300]}"

            await cache.store(run_id=run_id, summary=summary, label="failure")

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)


    async def _try_trigger_auto_learner_from_exception(

        self, state: LoopState, exc: Exception, stop_reason: str

    ) -> None:

        """Trigger AutoLearner from unhandled loop exception (always fires, fire-and-forget)."""

        try:

            from core.harness.learning import get_auto_learner

            learner = get_auto_learner()

            

            agent_id = str(state.context.get("_agent_id") or state.context.get("agent_id") or "")

            run_id = str(state.context.get("_run_id") or state.context.get("run_id") or "")

            task = str(state.context.get("task") or "")

            error_msg = f"{type(exc).__name__}: {exc}"

            

            draft = learner.analyze_failure(

                error=error_msg[:500],

                agent_id=agent_id,

                run_id=run_id,

                task=task,

                suggested_fix="",

            )

            learner.submit_for_review(draft)

            

            logging.getLogger("harness.learning").warning(

                "AutoLearner: generated SkillDraft '%s' from exception run_id=%s reason=%s",

                draft.name, run_id, stop_reason,

            )

        except Exception:

            logging.getLogger("harness.learning").debug(

                "AutoLearner exception handler skipped", exc_info=True

            )

        

        # CMM + ExperienceVector: feed exception to learning pipeline

        try:

            from core.harness.memory.pattern_accumulator import get_pattern_accumulator

            from core.harness.learning.experience_vector import get_experience_cache

            run_id = str(state.context.get("_run_id") or state.context.get("run_id") or "")

            agent_id = str(state.context.get("_agent_id") or state.context.get("agent_id") or "")

            tenant_id = str(state.context.get("tenant_id", ""))

            

            pa = get_pattern_accumulator()

            await pa.extract_from_failure(

                run_id=run_id,

                error_context={"error": str(exc)[:300], "agent_id": agent_id},

                tenant_id=tenant_id,

            )

            

            cache = get_experience_cache()

            await cache.store(

                run_id=run_id,

                summary=f"[{agent_id}] Exception: {exc}",

                label="exception",

            )

        except Exception:

            logging.getLogger(__name__).debug('_try_trigger_auto_learner_from_exception failed', exc_info=True)


    async def _try_feed_learning_pipeline(

        self, state: LoopState, user_msg: str, assistant_msg: str, stability: str

    ) -> None:

        """Feed every interaction into CMM PatternAccumulator and ExperienceVector.

        

        Successful runs build pattern memory; failures feed both pattern memory

        and experience cache for semantic retrieval by AutoLearner.

        Non-blocking — called via ensure_future.

        """

        run_id = str(state.context.get("_run_id") or state.context.get("run_id") or "")

        agent_id = str(state.context.get("_agent_id") or state.context.get("agent_id") or "")

        tenant_id = str(state.context.get("tenant_id", ""))

        

        # ── PatternAccumulator: extract tool-call fingerprints ──

        try:

            from core.harness.memory.pattern_accumulator import get_pattern_accumulator

            pa = get_pattern_accumulator()

            await pa.extract_from_run(run_id=run_id, tenant_id=tenant_id)

        except Exception:

            logging.getLogger(__name__).debug('_try_feed_learning_pipeline failed', exc_info=True)
        

        # ── ExperienceVector: store this interaction ──

        try:

            from core.harness.learning.experience_vector import get_experience_cache

            cache = get_experience_cache()

            label = "failure" if stability == "low" else "success"

            summary = f"[{agent_id}] User: {user_msg[:150]} | Agent: {assistant_msg[:150]}"

            await cache.store(run_id=run_id, summary=summary, label=label)

        except Exception:

            logging.getLogger(__name__).debug('_try_feed_learning_pipeline failed', exc_info=True)


        # ── SkillOpt: dual-channel analysis — analyze successful trajectories too ──

        if stability != "low" and assistant_msg:

            try:

                from core.harness.learning import get_auto_learner

                learner = get_auto_learner()

                task = str(state.context.get("task") or user_msg[:200])

                learner.analyze_success(

                    task=task, agent_id=agent_id,

                    run_id=run_id, trajectory_summary=assistant_msg[:500],

                )

            except Exception:

                logging.getLogger(__name__).debug('_try_feed_learning_pipeline failed', exc_info=True)


        # ── MetaClaw: compare success vs failure for this agent's tasks ──

        try:

            from core.harness.memory.pattern_accumulator import get_pattern_accumulator

            pa = get_pattern_accumulator()

            await pa.compare_success_failure(intent=agent_id)

        except Exception:

            logging.getLogger(__name__).debug('_try_feed_learning_pipeline failed', exc_info=True)


        # ── PatternCache: store execution pattern for future skip-stage optimization ──

        try:

            from core.harness.execution.pattern_cache import get_pattern_cache

            pcache = get_pattern_cache()

            task_type = str(state.context.get("task_type") or "")

            await pcache.store(

                domain_id=agent_id,

                query=user_msg,

                execution_path={

                    "task_type": task_type,

                    "stability": stability,

                },

                success=(stability != "low"),

            )

        except Exception:

            logging.getLogger(__name__).debug('_try_feed_learning_pipeline failed', exc_info=True)


    async def _try_extract_user_facts(self, state: LoopState, user_msg: str) -> None:

        u"""L3: Auto-extract structured facts from user messages.



        Detects patterns like "my budget is X", "my name is Y" and updates LearnerProfile.

        Mimics ChatGPT's "Memory updated" behavior.

        """

        import re, logging

        try:

            user_msg_str = str(user_msg) if not isinstance(user_msg, str) else user_msg

            facts = {}

            from core.harness.utils.zh_language import FACT_BUDGET_RE, FACT_NAME_RE, FACT_GOAL_RE

            budget_match = re.search(FACT_BUDGET_RE, user_msg_str)

            if budget_match:

                facts["budget"] = int(budget_match.group(1))



            name_match = re.search(FACT_NAME_RE, user_msg_str)

            if name_match:

                facts["name"] = name_match.group(1)



            goal_match = re.search(FACT_GOAL_RE, user_msg_str)

            if goal_match and len(goal_match.group(1)) > 3:

                facts["goals"] = goal_match.group(1).strip()



            if facts:

                from core.harness.knowledge.learning_ontology import (

                    load_learner_profile, save_learner_profile,

                )

                learner_id = state.context.get("_user_id", state.context.get("_agent_id", "user"))

                profile = load_learner_profile(learner_id)

                if profile:

                    changed = False

                    for k, v in facts.items():

                        if hasattr(profile, k):

                            setattr(profile, k, v)

                            changed = True

                    if changed:

                        save_learner_profile(profile)

                        logging.getLogger("harness.loop").info(

                            "Memory updated: %s → %s", learner_id, str(facts),

                        )

        except Exception as e:

            logging.warning(str(e), exc_info=True)



    # ── DELEGATED to graph_injector.py (extracted for SRP per §5.75) ──

    async def _try_inject_graph_context(self, state: LoopState):

        """Delegate to graph_injector.inject_graph_context — extracted from loop.py."""

        return await inject_graph_context(state)

    # ── DELEGATED to graph_injector.py (extracted for SRP per §5.75) ──

    async def _try_inject_memory_reminders(self, state: LoopState):

        """Delegate to graph_injector.inject_memory_reminders — extracted from loop.py."""

        return await inject_memory_reminders(state)



    async def _try_inject_ontology_context(self, state: LoopState):

        """Delegate to graph_injector.inject_ontology_context (v2.6)."""

        return await inject_ontology_context(state)

    # ── DELEGATED to compressor.py (extracted for SRP per §5.75) ──

    async def _maybe_compact_messages(self, state: LoopState):

        """Delegate to compressor.compact_messages — extracted from loop.py."""

        return await compact_messages(state, self._config, loop=self)

    def _build_compaction_prompt(self, ids_list: list, head: list) -> str:

        """Build compaction prompt from template (§8: engine code must not contain business SOP)."""

        from core.harness.assembly.compaction_prompt import get_compaction_prompt

        history_lines = [f"{m.get('role','user')}: {m.get('content','')}" for m in head if isinstance(m, dict)]

        return get_compaction_prompt(identifiers=ids_list, history_lines=history_lines)



    def _build_tools_desc(self) -> Tuple[str, Dict[str, Any]]:

        """

        Build a compact tools description string with budgets.



        Why:

        - MCP / tool ecosystems can grow large; dumping full descriptions every turn is expensive.

        - Claude Code uses dynamic MCP discovery; as a first step we apply budgets + observability.

        """

        import os



        per_tool_max = int(os.getenv("AIPLAT_TOOL_DESC_PER_TOOL_MAX_CHARS", "400") or "400")

        total_max = int(os.getenv("AIPLAT_TOOLS_DESC_MAX_CHARS", "4000") or "4000")



        stats: Dict[str, Any] = {

            "per_tool_max_chars": per_tool_max,

            "total_max_chars": total_max,

            "tools_total": len(self._tools or []),

            "tools_included": 0,

            "tools_hidden": 0,

            "tools_truncated": 0,

            "chars_total": 0,

        }



        if not self._tools:

            return "No tools available", stats



        # Ensure tool_search is always visible to the model when tools are truncated.
        # Code meta-tool: pin when deterministic intent matches (article: Turing escape hatch).

        always_include = {"tool_search"}

        try:
            from core.harness.execution.meta_tool import (
                ensure_code_meta_tool,
                meta_tool_pin_names,
                tool_names_from_tools,
            )

            _task0 = ""
            _ctx0 = {}
            if getattr(self, "_current_state", None) is not None:
                _ctx0 = self._current_state.context if isinstance(self._current_state.context, dict) else {}
                _task0 = str(_ctx0.get("task") or _ctx0.get("_user_task") or "")
            self._tools = ensure_code_meta_tool(
                list(self._tools or []),
                task=_task0,
                context=_ctx0 if isinstance(_ctx0, dict) else None,
            )
            always_include |= meta_tool_pin_names(
                tool_names_from_tools(self._tools),
                task=_task0,
                context=_ctx0 if isinstance(_ctx0, dict) else None,
            )
        except Exception:
            logging.getLogger(__name__).debug("meta_tool pin skipped", exc_info=True)

        ordered = list(self._tools)



        # PR #3: sort the tool list according to ControlProfile.tool_rank_by

        try:

            from core.harness.meta.profile_registry import get_active_profile

            rank_by = get_active_profile().tool_rank_by

            if rank_by == "success_rate":

                # sort by historical tool success rate (higher success rate first)

                def _success_score(t):

                    name = getattr(t, "name", "")

                    # get the success rate from ToolDriftDetector or from the tool itself

                    success = getattr(t, "_success_rate", None)

                    if success is None:

                        try:

                            from core.harness.learning.tool_drift_detector import get_detector

                            stats = get_detector().get_stats(name)

                            success = stats.get("success_rate", 0.5) if stats else 0.5

                        except Exception:

                            success = 0.5

                    return (0 if name in always_include else 1, -success, name)

                ordered.sort(key=_success_score)

            elif rank_by == "relevance":

                # sort by semantic relevance (reserved; currently falls back to static ordering)

                ordered.sort(key=lambda x: (0 if getattr(x, "name", "") in always_include else 1,

                                            str(getattr(x, "name", ""))))

            else:

                # static: keep the current order

                ordered.sort(key=lambda x: (0 if getattr(x, "name", "") in always_include else 1,

                                            str(getattr(x, "name", ""))))

        except Exception:

            # fallback: static ordering

            ordered.sort(key=lambda x: (0 if getattr(x, "name", "") in always_include else 1,

                                        str(getattr(x, "name", ""))))



        lines: List[str] = []

        for t in ordered:

            try:

                name = getattr(t, "name", None) or (t.get_name() if hasattr(t, "get_name") else str(t))

            except Exception:

                name = str(t)

            try:

                desc = getattr(t, "description", None) or (t.get_description() if hasattr(t, "get_description") else "")

            except Exception:

                desc = ""



            desc = str(desc or "")

            if per_tool_max > 0 and len(desc) > per_tool_max:

                desc = desc[: max(0, per_tool_max - 16)] + " …(truncated)"

                stats["tools_truncated"] += 1



            # Inject parameter schema so LLM knows correct parameter names

            try:

                params = getattr(getattr(t, '_config', None), 'parameters', None)

                if params and isinstance(params, dict):

                    props = params.get('properties', {})

                    required = params.get('required', [])

                    if props:

                        parts = []

                        for pn, ps in props.items():

                            pt = ps.get('type', 'any') if isinstance(ps, dict) else 'any'

                            rq = '*' if pn in required else ''

                            parts.append(f"{pn}{rq}:{pt}")

                        if parts:

                            desc = f"Params({', '.join(parts)}). {desc}"

            except Exception as e:

                logging.warning(str(e), exc_info=True)



            # MCP tools: prepend server description so Agent knows which MCP this tool belongs to

            try:

                meta = getattr(t, "metadata", {}) or {}

                srv_desc = str(meta.get("mcp_server_description", "") or "")

                if srv_desc:

                    name = f"{name} [{srv_desc}]"

            except Exception as e:

                logging.warning(str(e), exc_info=True)



            line = f"- {name}: {desc}".strip()

            projected = stats["chars_total"] + len(line) + (1 if lines else 0)

            if total_max > 0 and projected > total_max:

                stats["tools_hidden"] = stats["tools_total"] - stats["tools_included"]

                break



            lines.append(line)

            stats["tools_included"] += 1

            stats["chars_total"] = projected



        if stats["tools_hidden"]:

            lines.append(f"... ({stats['tools_hidden']} tools hidden; use tool search/narrow toolset)")



        # P1-1: dynamically highlight the 3 most relevant tools (without changing physical order; append a hint at the end)

        try:

            task = self._current_state.context.get("task", "")

            tool_names = [getattr(t, "name", str(t)) for t in (self._tools or [])]

            if task and len(tool_names) > 3:

                from core.harness.memory.compression import get_cached_embedding

                task_vec = get_cached_embedding(task)

                if task_vec is not None:

                    import numpy as np

                    tool_scores = []

                    for name in tool_names:

                        desc_vec = get_cached_embedding(str(name)[:300])

                        if desc_vec is not None:

                            score = float(np.dot(task_vec, desc_vec) / (

                                np.linalg.norm(task_vec) * np.linalg.norm(desc_vec) + 1e-8))

                            tool_scores.append((name, score))

                    top3 = sorted(tool_scores, key=lambda x: -x[1])[:3]

                    if top3:

                        names = ", ".join(f"`{name}`" for name, _ in top3)

                        lines.append(f"\n[TOOL HINT] Task may benefit from: {names}. "

                                     f"All tools remain available below.")

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)

        # Code meta-tool overlay (ephemeral; does not reorder — prompt-cache safe)
        try:
            from core.harness.execution.meta_tool import build_meta_tool_hint, tool_names_from_tools

            _ctx_m = {}
            _task_m = ""
            if getattr(self, "_current_state", None) is not None:
                _ctx_m = self._current_state.context if isinstance(self._current_state.context, dict) else {}
                _task_m = str(_ctx_m.get("task") or _ctx_m.get("_user_task") or "")
            _hint = build_meta_tool_hint(
                _task_m,
                tool_names_from_tools(self._tools),
                context=_ctx_m if isinstance(_ctx_m, dict) else None,
            )
            if _hint:
                lines.append("\n" + _hint)
                stats["meta_tool_hint"] = True
        except Exception:
            logging.getLogger(__name__).debug("meta_tool hint skipped", exc_info=True)

        return "\n".join(lines), stats



    def _build_skills_desc(self, *, context_pressure: Optional[float] = None) -> Tuple[str, Dict[str, Any]]:

        """

        Build a compact skills description string with budgets.



        Similar to OpenCode "find-skills" philosophy:

        - only expose a lightweight index (name + description)

        - for full SOP, use skill_load (on-demand)

        """

        import os



        per_skill_max = int(os.getenv("AIPLAT_SKILL_DESC_PER_SKILL_MAX_CHARS", "120") or "120")

        total_max = int(os.getenv("AIPLAT_SKILLS_DESC_MAX_CHARS", "1200") or "1200")

        default_sop_max = int(os.getenv("AIPLAT_SKILL_SOP_MAX_CHARS", "8000") or "8000")



        # P0: unified progressive disclosure budget (based on context pressure)

        try:

            from core.harness.context.skills_disclosure import compute_skills_disclosure_budget



            b = compute_skills_disclosure_budget(

                context_pressure=float(context_pressure or 0.0),

                default_per_skill_desc_max_chars=per_skill_max,

                default_skills_desc_total_max_chars=total_max,

                default_skill_sop_max_chars=default_sop_max,

            )

            per_skill_max = int(b.per_skill_desc_max_chars)

            total_max = int(b.skills_desc_total_max_chars)

            stats_policy = b.policy

            sop_hint = int(b.skill_sop_recommended_max_chars)

        except Exception:

            stats_policy = "normal"

            sop_hint = default_sop_max



        stats: Dict[str, Any] = {

            "per_skill_max_chars": per_skill_max,

            "total_max_chars": total_max,

            "disclosure_policy": stats_policy,

            "skill_sop_recommended_max_chars": sop_hint,

            "skills_total": 0,

            "skills_included": 0,

            "skills_hidden": 0,

            "skills_truncated": 0,

            "chars_total": 0,

        }



        stats["skills_total"] = len(self._skills or [])

        if not self._skills:

            return "No skills available (use skill_find to discover)", stats



        lines: List[str] = []

        # Sort skills by routing weight (learned), then alphabetically

        try:

            from core.harness.routing.skill_routing import get_skill_weight

            _get_weight = lambda s: get_skill_weight(

                str(getattr(s, 'name', None) or (getattr(s._config, 'name', '') if hasattr(s, '_config') else ''))

            )

        except Exception:

            _get_weight = lambda s: 1.0

        for skill in sorted(self._skills,

                            key=lambda s: (-_get_weight(s),

                                           str(getattr(s, 'name', getattr(getattr(s, '_config', None), 'name', '')) or ''))):

            try:

                name = getattr(skill, 'name', None) or (getattr(skill._config, 'name', '') if hasattr(skill, '_config') else '')

            except Exception:

                name = str(skill)

            name = str(name or '')

            # best-effort: hide denied skills (OpenCode behavior)

            try:

                perm_denied = False

                try:

                    from core.harness.integration import _ensure_di

                    di = _ensure_di()

                    if di:

                        r = di.resolve("SkillPermissionResolver")

                        if r and isinstance(r, dict):

                            perm_denied = r["resolve"](name) == "deny"

                except Exception:

                    logging.getLogger("harness.loop").warning("Permission resolver fallback", exc_info=True)

                if not perm_denied:

                    try:

                        from core.harness.integration import get_skill_permission_resolver

                        perm_denied = get_skill_permission_resolver()(name) == "deny"

                    except Exception:

                        logging.getLogger("harness.loop").warning("DI resolve fallback", exc_info=True)

                if perm_denied:

                    continue

            except Exception:

                logging.getLogger("harness.loop").warning("Skill enumeration best-effort", exc_info=True)

            try:

                cfg = getattr(skill, '_config', None) or (skill.get_config() if hasattr(skill, 'get_config') else None)

                desc = str(getattr(cfg, "description", "") or "")

                meta = dict(getattr(cfg, "metadata", {}) or {}) if cfg is not None else {}

                kind = str(meta.get("skill_kind") or "rule")

            except Exception:

                desc = ""

                kind = "rule"



            if per_skill_max > 0 and len(desc) > per_skill_max:

                desc = desc[: max(0, per_skill_max - 16)] + " …(truncated)"

                stats["skills_truncated"] += 1



            line = f"- {name} ({kind}): {desc}".strip()

            projected = stats["chars_total"] + len(line) + (1 if lines else 0)

            if total_max > 0 and projected > total_max:

                stats["skills_hidden"] = stats["skills_total"] - stats["skills_included"]

                break



            lines.append(line)

            stats["skills_included"] += 1

            stats["chars_total"] = projected



        if stats["skills_hidden"]:

            lines.append(f"... ({stats['skills_hidden']} skills hidden; use skill_find to search, and skill_load to load SOP)")

        # Hint (non-binding): advise an SOP budget when context is tight.

        if sop_hint and isinstance(sop_hint, int) and sop_hint > 0:

            lines.append(f"(hint) For SOP, call skill_load with max_chars≈{sop_hint}")



        return "\n".join(lines), stats



    # ── Action execution helpers (extracted from _act() per P1-6) ──



    def _init_routing_id(self, state: LoopState) -> str:

        routing_id = f"rtd_{uuid.uuid4().hex[:16]}"

        state.context["_routing_decision_id"] = routing_id

        return routing_id



    def _coding_policy_profile_for_skill(self, skill_obj: Any, state: LoopState) -> str:

        try:

            config = getattr(skill_obj, "_config", None) or getattr(skill_obj, "get_config", lambda: None)()

            meta = getattr(config, "metadata", None) if config is not None else None

            meta = meta if isinstance(meta, dict) else {}

            # Align with skill registry / PolicyGate: coding = file-output or uses_code_skill.
            is_coding = bool(meta.get("uses_code_skill") or meta.get("uses_file_output"))

            if not is_coding:

                return "off"

            from core.harness.utils.coding_intensity import (
                intensity_to_policy_profile,
                resolve_coding_intensity,
            )

            scope = str(state.context.get("skill_scope") or "engine").lower()

            inten = resolve_coding_intensity(
                explicit=state.context.get("_coding_intensity")
                or state.context.get("coding_intensity"),
                state=state.context if isinstance(state.context, dict) else None,
                scope=scope,
                default="full",
            )
            state.context["_coding_intensity"] = inten
            return intensity_to_policy_profile(inten)

        except Exception:

            return "off"



    async def _emit_routing_decision(

        self, state: LoopState, routing_decision_id: str,

        selected_kind: str, selected_name: str = "", query_excerpt: str = "",

    ) -> None:

        try:

            runtime = get_kernel_runtime()

            store = getattr(runtime, "execution_store", None) if runtime else None

            if store is None:

                return

            qx = str(query_excerpt or "").strip()

            if not qx:

                try:

                    msgs = state.context.get("messages") if isinstance(state.context.get("messages"), list) else []

                    for m in reversed(msgs):

                        if isinstance(m, dict) and str(m.get("role") or "").lower() == "user":

                            qx = str(m.get("content") or "").strip()

                            break

                except Exception:

                    qx = ""

                if not qx:

                    qx = str(state.context.get("task") or "").strip()

            end_ts = time.time()

            await store.add_syscall_event({

                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                "span_id": f"routing:decision:{state.context.get('_agent_id') or 'react'}:{int(getattr(state, 'step_count', 0) or 0)}",

                "parent_span_id": state.context.get("_current_step_span_id") or "",

                "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                "tenant_id": state.context.get("tenant_id"),

                "kind": "routing",

                "name": "routing_decision",

                "status": "decision",

                "start_time": end_ts, "end_time": end_ts, "duration_ms": 0.0,

                "args": {

                    "routing_decision_id": routing_decision_id,

                    "step_count": int(getattr(state, "step_count", 0) or 0),

                    "selected_kind": str(selected_kind),

                    "selected_name": str(selected_name or ""),

                    "selected_skill_id": str(selected_name or "") if str(selected_kind) == "skill" else "",

                    "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),

                    "query_excerpt": qx[:220],

                },

                "created_at": end_ts,

            })

        except Exception as e:

            logging.warning(str(e), exc_info=True)



    async def _emit_skill_candidates_snapshot(

        self, state: LoopState, routing_decision_id: str,

        selected_kind: str, selected_name: str = "",

    ) -> list:

        if os.getenv("AIPLAT_ENABLE_ROUTING_OBSERVABILITY", "") not in ("1", "true", "yes"):

            return []

        try:

            runtime = get_kernel_runtime()

            store = getattr(runtime, "execution_store", None) if runtime else None

            if store is None:

                return []

            q = ""

            try:

                msgs = state.context.get("messages") if isinstance(state.context.get("messages"), list) else []

                for m in reversed(msgs):

                    if isinstance(m, dict) and str(m.get("role") or "").lower() == "user":

                        q = str(m.get("content") or "").strip()

                        break

            except Exception:

                q = ""

            if not q:

                q = str(state.context.get("task") or "").strip()

            if not q:

                return []



            def _norm(s: str) -> str:

                s0 = str(s or "").lower().strip()

                s0 = re.sub(r"[\s\-\._/]+", " ", s0)

                s0 = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s0)

                return s0.strip()



            def _tokenize(s: str) -> set:

                s0 = _norm(s)

                if not s0:

                    return set()

                toks = set()

                for w in s0.split():

                    if len(w) >= 2:

                        toks.add(w)

                for seg in re.findall(r"[\u4e00-\u9fff]{2,}", s0):

                    for i in range(0, max(0, len(seg) - 1)):

                        toks.add(seg[i:i + 2])

                return toks



            qt = _tokenize(q)

            if not qt:

                return []

            candidates: list = []



            async def _scan_mgr(mgr, scope0):

                if mgr is None:

                    return

                try:

                    skills = await mgr.list_skills(None, None, 400, 0)

                except Exception:

                    skills = []

                for s in skills or []:

                    try:

                        sid = str(getattr(s, "id", "") or "")

                        nm = str(getattr(s, "name", "") or "")

                        desc = str(getattr(s, "description", "") or "")

                        meta = getattr(s, "metadata", None)

                        meta = meta if isinstance(meta, dict) else {}

                        skill_kind = str(meta.get("skill_kind") or "rule")

                        tc = meta.get("trigger_conditions") or meta.get("trigger_keywords") or []

                        kw = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}

                        blob = " ".join([nm, desc,

                            " ".join([str(x) for x in (tc or [])]),

                            " ".join([str(x) for x in (kw.get("objects") or [])]),

                            " ".join([str(x) for x in (kw.get("actions") or [])]),

                            " ".join([str(x) for x in (kw.get("constraints") or [])])])

                        st = _tokenize(blob)

                        if not st:

                            continue

                        inter = qt & st

                        if not inter:

                            continue

                        score = float(len(inter))

                        for t in (tc or [])[:10]:

                            if str(t or "").strip() and str(t).strip() in q:

                                score += 3.0

                                break

                        perm = None; exec_perm = None

                        try:

                            # DI: resolve_skill_permission via SkillPermissionResolver (see integration.py _ensure_di), resolve_executable_skill_permission

                            from core.api.core_facade import resolve_skill_permission, resolve_executable_skill_permission

                            perm = resolve_skill_permission(nm)

                            if skill_kind == "executable":

                                exec_perm = resolve_executable_skill_permission(nm)

                        except Exception as e:

                            logging.warning(str(e), exc_info=True)

                        candidates.append({

                            "skill_id": sid, "name": nm, "scope": scope0, "skill_kind": skill_kind,

                            "score": score, "overlap": sorted(list(inter))[:12],

                            "perm": perm, "exec_perm": exec_perm,

                        })

                    except Exception:

                        continue



            await _scan_mgr(getattr(runtime, "workspace_skill_manager", None), "workspace")

            await _scan_mgr(getattr(runtime, "skill_manager", None), "engine")

            candidates.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)

            top = candidates[:8]

            end_ts = time.time()

            await store.add_syscall_event({

                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                "tenant_id": state.context.get("tenant_id"),

                "kind": "routing", "name": "skill_candidates_snapshot", "status": "snapshot",

                "start_time": end_ts, "end_time": end_ts, "duration_ms": 0.0,

                "args": {

                    "routing_decision_id": routing_decision_id,

                    "step_count": int(getattr(state, "step_count", 0) or 0),

                    "selected_kind": selected_kind, "selected_name": selected_name,

                    "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),

                    "query_excerpt": q[:220], "candidates": top,

                },

                "created_at": end_ts,

            })

            return top

        except Exception:

            return []



    async def _emit_routing_strict_eval(

        self, state: LoopState, routing_decision_id: str,

        selected_kind: str, selected_name: str, candidates_top: list,

    ) -> None:

        try:

            runtime = get_kernel_runtime()

            store = getattr(runtime, "execution_store", None) if runtime else None

            if store is None:

                return

            thr = float(os.getenv("AIPLAT_ROUTING_STRICT_MIN_SCORE", "3.0") or "3.0")

            eligible = None

            gated_top1_reason = None

            top1 = candidates_top[0] if candidates_top and isinstance(candidates_top[0], dict) else None

            if top1 is not None:

                try:

                    if str(top1.get("perm") or "") == "deny":

                        gated_top1_reason = "permission_deny"

                    elif str(top1.get("skill_kind") or "") == "executable" and str(top1.get("exec_perm") or "") == "ask":

                        gated_top1_reason = "approval_required"

                except Exception as e:

                    logging.warning(str(e), exc_info=True)

            for c in candidates_top or []:

                if not isinstance(c, dict):

                    continue

                try:

                    if str(c.get("perm") or "") == "deny":

                        continue

                    if str(c.get("skill_kind") or "") == "executable" and str(c.get("exec_perm") or "") == "ask":

                        continue

                    eligible = c

                    break

                except Exception:

                    continue

            eligible_id = str((eligible or {}).get("skill_id") or (eligible or {}).get("name") or "")

            eligible_score = float((eligible or {}).get("score") or 0.0) if eligible else None

            strict_eligible = bool(eligible_id and eligible_score is not None and float(eligible_score) >= thr)

            sel_kind = str(selected_kind or "")

            sel_name = str(selected_name or "")

            outcome = "no_eligible"

            if strict_eligible:

                if sel_kind != "skill":

                    outcome = "miss_tool" if sel_kind == "tool" else "miss_no_action"

                else:

                    outcome = "hit" if sel_name == eligible_id else "misroute"

            end_ts = time.time()

            await store.add_syscall_event({

                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                "span_id": f"routing:strict:{state.context.get('_agent_id') or 'react'}:{int(getattr(state, 'step_count', 0) or 0)}",

                "parent_span_id": state.context.get("_current_step_span_id") or "",

                "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                "tenant_id": state.context.get("tenant_id"),

                "kind": "routing", "name": "routing_strict_eval", "status": "eval",

                "start_time": end_ts, "end_time": end_ts, "duration_ms": 0.0,

                "args": {

                    "routing_decision_id": routing_decision_id,

                    "step_count": int(getattr(state, "step_count", 0) or 0),

                    "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),

                    "threshold": thr, "selected_kind": sel_kind, "selected_name": sel_name,

                    "selected_skill_id": sel_name if sel_kind == "skill" else "",

                    "eligible_top1_skill_id": eligible_id, "eligible_top1_score": eligible_score,

                    "eligible_top1_exists": bool(eligible_id), "strict_eligible": strict_eligible,

                    "strict_outcome": outcome, "gated_top1_reason": gated_top1_reason,

                },

                "created_at": end_ts,

            })

        except Exception as e:

            logging.warning(str(e), exc_info=True)



    async def _emit_routing_explain(

        self, state: LoopState, routing_decision_id: str,

        selected_kind: str, selected_name: str, candidates_top: list,

        result_status: str = "", result_error: str = "",

    ) -> None:

        if os.getenv("AIPLAT_ENABLE_ROUTING_OBSERVABILITY", "") not in ("1", "true", "yes"):

            return

        try:

            runtime = get_kernel_runtime()

            store = getattr(runtime, "execution_store", None) if runtime else None

            if store is None:

                return

            qx = ""

            try:

                msgs = state.context.get("messages") if isinstance(state.context.get("messages"), list) else []

                for m in reversed(msgs):

                    if isinstance(m, dict) and str(m.get("role") or "").lower() == "user":

                        qx = str(m.get("content") or "").strip()

                        break

            except Exception:

                qx = ""

            if not qx:

                qx = str(state.context.get("task") or "").strip()

            sel_id = str(selected_name or "")

            top1 = candidates_top[0] if candidates_top and isinstance(candidates_top[0], dict) else {}

            top1_id = str(top1.get("skill_id") or top1.get("name") or "")

            top1_score = float(top1.get("score") or 0.0) if top1 else None

            sel_rank = None; sel_score = None

            for idx, c in enumerate(candidates_top or []):

                if not isinstance(c, dict):

                    continue

                if str(c.get("skill_id") or c.get("name") or "") == sel_id:

                    sel_rank = idx

                    sel_score = float(c.get("score") or 0.0)

                    break

            gap = None

            try:

                if top1_score is not None and sel_score is not None:

                    gap = float(top1_score - sel_score)

            except Exception as e:

                logging.warning(str(e), exc_info=True)

            top1_gate = None

            try:

                if str(top1.get("perm") or "") == "deny":

                    top1_gate = "permission_deny"

                elif str(top1.get("skill_kind") or "") == "executable" and str(top1.get("exec_perm") or "") == "ask":

                    top1_gate = "approval_required"

            except Exception as e:

                logging.warning(str(e), exc_info=True)

            end_ts = time.time()

            await store.add_syscall_event({

                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                "tenant_id": state.context.get("tenant_id"),

                "kind": "routing", "name": "routing_explain", "status": "explain",

                "start_time": end_ts, "end_time": end_ts, "duration_ms": 0.0,

                "args": {

                    "routing_decision_id": routing_decision_id,

                    "step_count": int(getattr(state, "step_count", 0) or 0),

                    "selected_kind": str(selected_kind), "selected_name": sel_id,

                    "selected_skill_id": sel_id if str(selected_kind) == "skill" else "",

                    "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),

                    "query_excerpt": qx[:220], "candidates_top": (candidates_top or [])[:5],

                    "top1_skill_id": top1_id, "top1_score": top1_score, "top1_gate_hint": top1_gate,

                    "selected_rank": sel_rank, "selected_score": sel_score, "score_gap": gap,

                    "result_status": str(result_status or ""), "result_error": str(result_error or ""),

                },

                "created_at": end_ts,

            })

        except Exception as e:

            logging.warning(str(e), exc_info=True)



    async def _emit_no_action(self, state: LoopState, routing_decision_id: str) -> None:

        await self._emit_routing_decision(state, routing_decision_id, "none")

        top = await self._emit_skill_candidates_snapshot(state, routing_decision_id, "none")

        await self._emit_routing_strict_eval(state, routing_decision_id, "none", "", top)

        await self._emit_routing_explain(state, routing_decision_id, "none", "", top, "no_action", "")



    async def _try_file_syscall(self, tool_name: str, tool_args: dict, state: LoopState):

        """Dispatch file/code syscalls as a fallback when no registered tool matches."""

        name = str(tool_name).strip().lower()

        try:

            if name == "read" or name == "sys_file_read":

                from core.harness.syscalls.file import sys_file_read

                path = str((tool_args or {}).get("path", "") or (tool_args or {}).get("filePath", ""))

                result = await sys_file_read(path, trace_context={"source": "loop_fallback"})

                return json.dumps(result, ensure_ascii=False)

            elif name == "write" or name == "sys_file_write":

                from core.harness.syscalls.file import sys_file_write

                path = str((tool_args or {}).get("path", "") or (tool_args or {}).get("filePath", ""))

                content = str((tool_args or {}).get("content", ""))

                result = await sys_file_write(path, content, trace_context={"source": "loop_fallback"})

                return json.dumps(result, ensure_ascii=False)

            elif name == "edit" or name == "sys_file_edit":

                from core.harness.syscalls.file import sys_file_edit

                path = str((tool_args or {}).get("path", "") or (tool_args or {}).get("filePath", ""))

                old_str = str((tool_args or {}).get("old_string", "") or (tool_args or {}).get("oldString", ""))

                new_str = str((tool_args or {}).get("new_string", "") or (tool_args or {}).get("newString", ""))

                result = await sys_file_edit(path, old_str, new_str, trace_context={"source": "loop_fallback"})

                return json.dumps(result, ensure_ascii=False)

            elif name in ("glob", "sys_glob"):

                from core.harness.syscalls.code import sys_glob

                pattern = str((tool_args or {}).get("pattern", "") or (tool_args or {}).get("glob", ""))

                result = await sys_glob(pattern, trace_context={"source": "loop_fallback"})

                return json.dumps(result, ensure_ascii=False)

            elif name in ("grep", "codesearch", "sys_code_search", "search"):

                from core.harness.syscalls.code import sys_code_search

                pattern = str((tool_args or {}).get("pattern", "") or (tool_args or {}).get("query", ""))

                include = str((tool_args or {}).get("include", "") or (tool_args or {}).get("fileTypes", ""))

                result = await sys_code_search(pattern, include=include, trace_context={"source": "loop_fallback"})

                return json.dumps(result, ensure_ascii=False)

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        return None




    @staticmethod
    def _inject_user_task_into_skill_args(state: LoopState, skill_args: Any) -> Dict[str, Any]:
        """Ensure skill_call carries the user PRD/task, not the skill's own description.

        Models often pass ``input=`` as the skill SOP blurb and drop the real user
        brief — quality gates then fail on constraints that the skill never saw.
        """
        from core.harness.utils.execute_session import skill_arg_payload_is_thin

        args: Dict[str, Any] = dict(skill_args) if isinstance(skill_args, dict) else {}
        user_task = str(state.context.get("_user_task") or "").strip()
        if not user_task:
            raw_task = str(state.context.get("task") or "").strip()
            if "## Task\n" in raw_task:
                user_task = raw_task.split("## Task\n", 1)[1].strip()
            else:
                user_task = raw_task
        if len(user_task) < 40:
            return args

        input_keys = ("input", "prd", "message", "user_requirement", "text", "content")
        used_key = next((k for k in input_keys if str(args.get(k) or "").strip()), None)

        if used_key is None:
            args["input"] = user_task
        elif skill_arg_payload_is_thin(str(args.get(used_key) or ""), user_task):
            args[used_key] = user_task
        return args

    @staticmethod
    def _inject_execute_payload_into_skill_args(
        state: LoopState, skill_args: Any
    ) -> Dict[str, Any]:
        """Copy structured execute JSON fields the model omitted from skill_call.

        Management execute sends ``{message, test_cases, ...}``. Models often call
        ``test_executor`` with only a short ``input=`` so the handler sees 0 cases
        (run-74a19d55326c) then the loop waits for a second DONE LLM that never starts.
        """
        args: Dict[str, Any] = dict(skill_args) if isinstance(skill_args, dict) else {}
        raw = state.context.get("_execute_input")
        if not isinstance(raw, dict):
            return args
        for key in (
            "test_cases",
            "agent_app",
            "frontend_pages",
            "prd",
            "project",
            "target_agent_id",
            "max_traces",
            "force",
        ):
            cur = args.get(key)
            if isinstance(cur, (list, dict)) and not cur:
                cur = None
            if cur not in (None, "", [], {}):
                continue
            val = raw.get(key)
            if val in (None, "", [], {}):
                continue
            args[key] = val
        return args

    @staticmethod
    def _inject_preferred_language_into_skill_args(
        state: LoopState,
        skill_name: str,
        skill_args: Any,
    ) -> Dict[str, Any]:
        """Fill ``language`` for code_generation from AGENT preferred_language.

        Priority: language named in user task → agent ``_preferred_language`` →
        explicit skill arg (model) → leave unset (skill schema default).

        Model args are lowest because the schema default is often ``python`` and
        local models echo it even for FE agents (preferred_language must win).
        Config-driven; never keys off agent_id.
        """
        args: Dict[str, Any] = dict(skill_args) if isinstance(skill_args, dict) else {}
        name = str(skill_name or "").strip().lower().replace("-", "_")
        if name not in ("code_generation",):
            return args
        user_task = str(state.context.get("_user_task") or "").strip()
        if not user_task:
            raw_task = str(state.context.get("task") or "").strip()
            if "## Task\n" in raw_task:
                user_task = raw_task.split("## Task\n", 1)[1].strip()
            else:
                user_task = raw_task
        chosen = ""
        try:
            from core.management.execution_quality_review import (
                _detect_requested_code_language,
            )

            req = _detect_requested_code_language(user_task)
            if req:
                chosen = str(req).strip().lower()
        except Exception:
            logging.getLogger(__name__).debug(
                "preferred_language task detect skipped", exc_info=True
            )
        if not chosen:
            pref = str(state.context.get("_preferred_language") or "").strip().lower()
            if pref:
                chosen = pref
        if not chosen:
            chosen = str(args.get("language") or "").strip().lower()
        if chosen:
            args["language"] = chosen
            # Prevent code_generation from silently adopting a mismatched body language.
            args["_language_locked"] = True
        return args

    @staticmethod
    def _primary_skill_text(state: LoopState) -> str:
        """Primary skill body even when skill_delivery is not once (qa / conversational)."""
        raw = state.context.get("_primary_skill_output")
        try:
            from core.harness.utils.inline_autoreview_workspace import (
                coerce_inline_delivery_text,
            )

            body = coerce_inline_delivery_text(raw).split("[DELIVERY]", 1)[0].strip()
        except Exception:
            body = str(raw or "").split("[DELIVERY]", 1)[0].strip()
        if not body.strip():
            return ""
        # Drop the soft "already delivered" wrapper if present
        if body.startswith("[skill_delivery=once]"):
            parts = body.split("\n\n", 1)
            body = parts[1].strip() if len(parts) > 1 else body
        return body if len(body) >= 40 else ""

    @staticmethod
    def _skill_delivery_body(state: LoopState) -> str:
        """Alias used by observe/auto_done — must exist or skill_delivery=once AttributeError hangs step_1."""
        return ReActLoop._primary_skill_text(state)

    def _finalize_with_skill_delivery(self, state: LoopState) -> bool:
        """If primary skill already delivered, promote it to final output and finish."""
        body = self._skill_delivery_body(state)
        if not body:
            return False
        try:
            from core.management.execution_quality_review import (
                is_non_deliverable_coding_output,
            )

            _in = str(state.context.get("_user_task") or "").strip()
            if is_non_deliverable_coding_output(
                input_text=_in,
                output_text=body,
                raw_out={"text": body},
                hints=" ".join(self._resolved_bound_skill_ids(state)),
                scope="skill",
            ):
                # Do not greenwash clarify / thin stubs into completed
                state.context.pop("_primary_skill_delivered", None)
                state.context.pop("_primary_skill_output", None)
                return False
        except Exception:
            logging.getLogger(__name__).debug(
                "skill_delivery finalize substance check skipped", exc_info=True
            )
        state.context["output"] = body
        state.context["_skill_delivery_finalized"] = True
        try:
            from core.services.execution_store import get_execution_store
            import asyncio
            # best-effort sync emit via creating task is awkward here; inline await below in callers
        except Exception:
            pass  # noqa: cleanup-best-effort
        state.current = LoopStateEnum.FINISHED
        return True

    async def _close_leftover_running_syscalls(
        self, state: LoopState, *, status: str = "ok", error: str = ""
    ) -> None:
        """Flip leftover running syscall rows after the loop already declared done."""
        import asyncio as _aio_close

        try:
            from core.services.execution_store import get_execution_store

            rid = str(state.context.get("_run_id") or "")
            store = get_execution_store()
            if not rid or not hasattr(store, "close_running_syscall_events"):
                return
            await _aio_close.wait_for(
                store.close_running_syscall_events(
                    rid,
                    status=status,
                    error=error or None,
                ),
                timeout=3.0,
            )
        except Exception:
            logging.getLogger(__name__).debug(
                "close leftover syscalls skipped", exc_info=True
            )

    async def _eager_finalize_agent_row(
        self, state: LoopState, *, output_text: str, source: str
    ) -> bool:
        """Upsert Agent row + seal RunGraph before POST_LOOP can hang the UI on running."""
        # Close stepped + legacy pre-LLM prep before QR/store can stall.
        # Open id is ``{run}:pre_llm_prep:{step}``; a legacy-only close leaves
        # the canvas card running (qa_agent run-124d89d5ef3f).
        # Must be bounded: an un-timed SQLite lock here never reaches upsert.
        try:
            import asyncio as _aio_prep_ef

            rid_prep = str(state.context.get("_run_id") or "")
            if rid_prep:
                from core.harness.utils.execute_session import emit_pre_llm_prep_close
                from core.services.execution_store import get_execution_store as _ges_ef

                await _aio_prep_ef.wait_for(
                    emit_pre_llm_prep_close(
                        _ges_ef(),
                        rid_prep,
                        status="ok",
                        step_count=state.step_count,
                        parent_span_id=str(state.context.get("_current_step_span_id") or ""),
                        reason=f"eager_finalize:{source}",
                    ),
                    timeout=2.0,
                )
        except Exception:
            logging.getLogger(__name__).debug(
                "eager finalize pre_llm_prep close skipped", exc_info=True
            )
        if state.context.get("_agent_row_finalized"):
            return True
        body = str(output_text or "").strip()
        if len(body) < 20:
            return False
        try:
            import asyncio as _aio_fin

            from core.harness.utils.execute_session import (
                finalize_agent_after_skill_delivery,
            )

            ok = await _aio_fin.wait_for(
                finalize_agent_after_skill_delivery(
                    run_id=str(state.context.get("_run_id") or ""),
                    agent_id=str(state.context.get("_agent_id") or ""),
                    output_text=body,
                    trace_id=str(
                        state.context.get("_trace_id")
                        or state.context.get("trace_id")
                        or ""
                    ),
                    metadata_extra={
                        "finalize_source": source,
                        "user_task": str(state.context.get("_user_task") or "")[:8000],
                        "bound_skills": list(self._resolved_bound_skill_ids(state)),
                        "coding_veto_exhausted": bool(state.context.get("_coding_veto_exhausted")),
                        "coding_veto_last_reason": str(
                            state.context.get("_coding_veto_last_reason") or ""
                        )[:500],
                    },
                ),
                timeout=12.0,
            )
            if ok:
                state.context["_agent_row_finalized"] = True
            return bool(ok)
        except Exception:
            logging.getLogger(__name__).warning(
                "%s eager finalize failed run_id=%s",
                source,
                state.context.get("_run_id"),
                exc_info=True,
            )
            return False


    async def _dispatch_skill_call(

        self, state: LoopState, parsed: Any, routing_decision_id: str

    ) -> str:

        skill_name = parsed.name

        skill_args = parsed.args if isinstance(getattr(parsed, "args", None), dict) else {}
        skill_args = self._inject_user_task_into_skill_args(state, skill_args)
        skill_args = self._inject_execute_payload_into_skill_args(state, skill_args)
        skill_args = self._inject_preferred_language_into_skill_args(
            state, str(skill_name or ""), skill_args
        )
        # Pass Agent required_skills so PolicyGate can waive second HITL.
        skill_args = dict(skill_args) if isinstance(skill_args, dict) else {}
        bound = self._resolved_bound_skill_ids(state)
        if bound:
            skill_args["_bound_skill_ids"] = list(bound)
        # Coding follow-up: stock engine autoreview only speaks load_diff(target).
        # Materialize ## FILE body into a temp worktree; pass path via skill param
        # ``_git_work_tree`` (never mutate process-global GIT_* across LLM await).
        inline_for_ar = ""
        if str(skill_name or "").strip().lower() == "autoreview":
            if not str(skill_args.get("target") or "").strip():
                skill_args["target"] = "diff"
            body = self._skill_delivery_body(state)
            if not body:
                try:
                    from core.harness.utils.inline_autoreview_workspace import (
                        coerce_inline_delivery_text,
                    )

                    body = coerce_inline_delivery_text(
                        state.context.get("_primary_skill_output")
                    ).split("[DELIVERY]", 1)[0].strip()
                except Exception:
                    body = str(state.context.get("_primary_skill_output") or "").split(
                        "[DELIVERY]", 1
                    )[0].strip()
            inline_for_ar = str(
                skill_args.pop("inline_code", "") or skill_args.pop("code", "") or ""
            ).strip()
            if not inline_for_ar and body and ("## FILE" in body or "```" in body):
                inline_for_ar = body[:80000]

        state.context["skill_call"] = {"skill": skill_name, "args": skill_args, "format": parsed.format}

        prof = "off"

        for skill in self._skills:

            name = ""

            if hasattr(skill, "name"):

                name = str(getattr(skill, "name", "") or "")

            elif hasattr(skill, "_config") and getattr(skill, "_config", None) is not None:

                name = str(getattr(skill._config, "name", "") or "")

            if name.strip().lower() == skill_name.strip().lower():

                prof = self._coding_policy_profile_for_skill(skill, state)

                state.context["_coding_policy_profile"] = prof

                await self._emit_routing_decision(state, routing_decision_id, "skill", str(skill_name))

                # Observability + PRE_SKILL_USE must not run on the skill hot path.
                # wait_for cannot interrupt a sync list_skills / hook (test_executor
                # run-e6d421dfd25e: routing_decision then 4min with no skill_route).
                import asyncio as _aio_pre_sk
                top: list = []

                async def _pre_skill_obs() -> None:
                    try:
                        snap = await self._emit_skill_candidates_snapshot(
                            state, routing_decision_id, "skill", str(skill_name)
                        )
                        await self._emit_routing_strict_eval(
                            state, routing_decision_id, "skill", str(skill_name), snap
                        )
                        await self._trigger_hook(
                            HookPhase.PRE_SKILL_USE,
                            {"skill": skill_name, "skill_args": skill_args, "format": parsed.format},
                        )
                    except Exception:
                        logging.getLogger(__name__).debug(
                            "pre-skill observability/hook skipped", exc_info=True
                        )

                try:
                    _aio_pre_sk.ensure_future(_pre_skill_obs())
                except Exception:
                    logging.getLogger(__name__).debug(
                        "pre-skill observability schedule skipped", exc_info=True
                    )

                from ...interfaces import SkillContext

                try:

                    skill_context = SkillContext(

                        session_id=state.context.get("session_id", "default"),

                        user_id=state.context.get("user_id", "system"),

                        variables=skill_args,

                    )

                    _run_id = state.context.get("_run_id")
                    _step_span = state.context.get("_current_step_span_id")

                    if isinstance(skill_context.variables, dict):
                        if _run_id:
                            skill_context.variables["_run_id"] = _run_id
                        if _step_span:
                            skill_context.variables["_parent_span_id"] = _step_span

                    _skill_timeout = None
                    try:
                        _cfg_to = getattr(skill, "_config", None)
                        _meta_to = getattr(_cfg_to, "metadata", None) if _cfg_to else None
                        if isinstance(_meta_to, dict) and _meta_to.get("timeout") is not None:
                            _skill_timeout = float(_meta_to.get("timeout"))
                    except Exception:
                        _skill_timeout = None

                    async def _do_skill_call():
                        return await sys_skill_call(

                            skill, skill_args, context=skill_context,

                            user_id=skill_context.user_id, session_id=skill_context.session_id,

                            timeout_seconds=_skill_timeout,

                            trace_context={

                                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                                "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                                "parent_span_id": _step_span,

                                "tenant_id": state.context.get("tenant_id"),

                                "routing_decision_id": routing_decision_id,

                                "coding_policy_profile": prof,

                                "routing_candidates_emitted": True,

                                "_bound_skill_ids": list(bound),

                            },

                        )

                    if inline_for_ar:
                        from types import SimpleNamespace

                        from core.harness.utils.inline_autoreview_workspace import (
                            autoreview_git_env_for_inline,
                            staged_inline_worktree,
                        )

                        # Explicit worktree path only — never GIT_* + ambient cwd.
                        with staged_inline_worktree(inline_for_ar) as _ar_wt:
                            if _ar_wt is None:
                                result = SimpleNamespace(
                                    success=True,
                                    error=None,
                                    output=(
                                        "No changes to review "
                                        "(inline git staging produced empty diff)."
                                    ),
                                    metadata={"inline_staging": "empty"},
                                )
                            else:
                                skill_args["_git_work_tree"] = _ar_wt
                                skill_args["_require_git_work_tree"] = True
                                if isinstance(skill_context.variables, dict):
                                    skill_context.variables["_git_work_tree"] = _ar_wt
                                    skill_context.variables["_require_git_work_tree"] = True
                                result = await _do_skill_call()
                    else:
                        result = await _do_skill_call()

                    if getattr(result, "error", None) == "approval_required":

                        state.context["error"] = "approval_required"

                        state.context["approval"] = getattr(result, "metadata", {}) or {}

                        _sn = str(skill_name or "").strip()
                        _follow_ids = {"autoreview", "code_review", "code-hygiene"}
                        if _sn in _follow_ids:
                            prev = state.context.get("_followup_skills_done") or []
                            if not isinstance(prev, list):
                                prev = []
                            if _sn not in prev:
                                state.context["_followup_skills_done"] = [*prev, _sn]
                            # Coding skill_delivery=once: HITL pause on follow-up review
                            # wedges the run (nested LLM / cancel hangs). Mark attempted,
                            # continue to DONE; quality_review flags autoreview_incomplete.
                            if str(state.context.get("_skill_delivery") or "").lower() == "once":
                                state.metadata["pause_requested"] = False
                                result_output = (
                                    f"Follow-up `{_sn}` returned approval_required "
                                    "(not blocking coding seal). Proceed to DONE with "
                                    "the primary skill output."
                                )
                            else:
                                state.metadata["pause_requested"] = True
                                result_output = "Approval required"
                        else:
                            state.metadata["pause_requested"] = True
                            result_output = "Approval required"

                    elif getattr(result, "error", None) == "policy_denied":

                        state.context["error"] = "policy_denied"

                        state.context["policy"] = getattr(result, "metadata", {}) or {}

                        state.metadata["pause_requested"] = True

                        result_output = "POLICY_DENIED"

                    # Phase 22 G4: Step-by-step confirmation mode

                    elif os.getenv("AIPLAT_STEP_CONFIRM_ENABLED", "").lower() in ("true", "1", "yes"):

                        state.metadata["pause_requested"] = True

                        state.metadata["step_confirm_tool"] = tool_name

                        result_output = f"[STEP CONFIRM] Tool '{tool_name}' requires human confirmation"

                    else:

                        # Surface failure so ReAct does not treat a rejected payload
                        # (e.g. architecture_lone_api) as a successful Observation.
                        if (not bool(getattr(result, "success", True))) or getattr(result, "error", None):
                            err = str(getattr(result, "error", None) or "skill_failed")
                            out = getattr(result, "output", None)
                            result_output = (
                                f"Skill error: {err}\n"
                                f"Rejected output (do not treat as final answer):\n"
                                f"{str(out)[:4000]}"
                            )
                        else:
                            result_output = result.output if hasattr(result, 'output') else str(result)

                except Exception as e:

                    result_output = f"Skill error: {e}"

                try:

                    st = "success" if getattr(result, "success", False) else "failed"

                    await self._emit_routing_explain(state, routing_decision_id, "skill", str(skill_name), top, st, str(getattr(result, "error", "") or ""))

                except Exception as e:

                    logging.warning(str(e), exc_info=True)

                await self._trigger_hook(HookPhase.POST_SKILL_USE, {"skill": skill_name, "result": result_output, "format": parsed.format})

                # Config-driven single delivery: remember success so next reason must DONE

                try:

                    ok = True

                    _res = locals().get("result")

                    if _res is not None:

                        ok = bool(getattr(_res, "success", True)) and not getattr(_res, "error", None)

                    out_s = str(result_output or "")

                    if out_s.startswith("Skill error:") or out_s.startswith("Denied:"):

                        ok = False

                    # Strip prior DELIVERY footer when measuring length

                    body = out_s.split("[DELIVERY]", 1)[0].strip()

                    # Thin / clarify stubs must not count as skill_delivery=once success.
                    # Only coding skills: a test_executor JSON report is not a code stub
                    # (run-74a19d55326c: report written, _primary_skill_delivered never set).
                    _skn = str(skill_name or "").strip().lower().replace("-", "_")
                    if ok and _skn in {
                        "code_generation",
                        "code_hygiene",
                        "file_operations",
                    }:
                        try:
                            from core.management.execution_quality_review import (
                                is_non_deliverable_coding_output,
                                _text_blob,
                            )
                            _raw_out = getattr(result, "output", None) if locals().get("result") is not None else None
                            _blob = _text_blob(_raw_out) if _raw_out is not None else body
                            _in = str(state.context.get("_user_task") or "").strip()
                            if is_non_deliverable_coding_output(
                                input_text=_in,
                                output_text=_blob or body,
                                raw_out=_raw_out if isinstance(_raw_out, dict) else {"text": _blob or body},
                                hints=" ".join(self._resolved_bound_skill_ids(state)),
                                scope="skill",
                            ):
                                ok = False
                        except Exception:
                            logging.getLogger(__name__).debug(
                                "thin_code_stub delivery guard skipped", exc_info=True
                            )

                    if ok and len(body) >= 40:

                        state.context["_primary_skill_delivered"] = str(skill_name)

                        try:
                            from core.harness.utils.inline_autoreview_workspace import (
                                coerce_inline_delivery_text,
                            )

                            _coerced = coerce_inline_delivery_text(
                                getattr(result, "output", None)
                                if locals().get("result") is not None
                                else out_s
                            )
                            state.context["_primary_skill_output"] = (
                                (_coerced.split("[DELIVERY]", 1)[0].strip() or out_s)
                                if _coerced.strip()
                                else out_s
                            )
                        except Exception:
                            state.context["_primary_skill_output"] = out_s

                        _follow_ids = {"autoreview", "code_review", "code-hygiene"}
                        if str(skill_name).strip() in _follow_ids:
                            prev = state.context.get("_followup_skills_done") or []
                            if not isinstance(prev, list):
                                prev = []
                            if str(skill_name) not in prev:
                                state.context["_followup_skills_done"] = [*prev, str(skill_name)]

                        if str(state.context.get("_skill_delivery") or "").lower() == "once":
                            nxt = self._pending_coding_followup(state)
                            if nxt and str(skill_name).strip() not in _follow_ids:
                                result_output = (
                                    f"{out_s}\n\n"
                                    f"[DELIVERY] Skill `{skill_name}` succeeded. "
                                    f"Next call `{nxt}` on the generated files, then DONE. "
                                    f"Do not re-call `{skill_name}`."
                                )
                            else:
                                result_output = (

                                f"{out_s}\n\n"

                                f"[DELIVERY] Skill `{skill_name}` succeeded. "

                                f"Next response MUST be {{\"type\":\"done\",\"answer\":...}} "

                                f"or DONE: summarizing this output. Do not re-call the same skill."

                            )

                except Exception:

                    logging.getLogger(__name__).debug("skill_delivery mark failed", exc_info=True)

                return str(result_output)

        return f"Skill not found: {skill_name}"



    async def _dispatch_tool_call(

        self, state: LoopState, parsed: Any, routing_decision_id: str

    ) -> str:

        tool_name = parsed.name

        tool_args = parsed.args

        state.context["tool_call"] = {"tool": tool_name, "args": tool_args, "format": parsed.format}

        state.context["_coding_policy_profile"] = "karpathy_v1"

        await self._emit_routing_decision(state, routing_decision_id, "tool", str(tool_name))

        top = await self._emit_skill_candidates_snapshot(state, routing_decision_id, "tool", str(tool_name))

        await self._emit_routing_strict_eval(state, routing_decision_id, "tool", str(tool_name), top)

        await self._emit_routing_explain(state, routing_decision_id, "tool", str(tool_name), top, "tool_selected", "")

        for tool in self._tools:

            if str(getattr(tool, 'name', '')).strip().lower() == str(tool_name).strip().lower():

                approval_results = await self._trigger_hook(

                    HookPhase.PRE_APPROVAL_CHECK,

                    {"tool_name": tool_name, "tool_args": tool_args, "context": state.context},

                )

                deny = _extract_deny(approval_results)

                if deny:

                    await self._trigger_hook(HookPhase.POST_APPROVAL_CHECK, {"tool_name": tool_name, "allowed": False, "reason": deny.get("reason")})

                    return f"Denied: {deny.get('reason', 'approval denied')}"

                self._approval_check(tool_name, state.context)

                await self._trigger_hook(HookPhase.PRE_TOOL_USE, {"tool_name": tool_name, "tool_args": tool_args, "format": parsed.format})

                try:

                    approval_meta = state.context.get("approval") if isinstance(state.context.get("approval"), dict) else {}

                    approval_req_id = approval_meta.get("approval_request_id")

                    if approval_req_id:

                        try:

                            tool_args = dict(tool_args or {})

                            tool_args["_approval_request_id"] = approval_req_id

                        except Exception as e:

                            logging.warning(str(e), exc_info=True)

                    result = await sys_tool_call(

                        tool, tool_args,

                        user_id=state.context.get("user_id", "system"),

                        session_id=state.context.get("session_id", "default"),

                        trace_context={

                            "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                            "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                            "parent_span_id": state.context.get("_current_step_span_id"),

                            "tenant_id": state.context.get("tenant_id"),

                            "routing_decision_id": routing_decision_id,

                            "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),

                        },

                    )

                    if getattr(result, "error", None) == "approval_required":

                        state.context["error"] = "approval_required"

                        state.context["approval"] = getattr(result, "metadata", {}) or {}

                        state.metadata["pause_requested"] = True

                        result_output = "Approval required"

                        ok = False

                    elif getattr(result, "error", None) == "policy_denied":

                        state.context["error"] = "policy_denied"

                        state.context["policy"] = getattr(result, "metadata", {}) or {}

                        denied_count = int(state.metadata.get("policy_denied", 0) or 0) + 1

                        state.metadata["policy_denied"] = denied_count

                        auto_retry = os.getenv("AIPLAT_POLICY_DENIED_AUTO_RETRY", "true").lower() in ("1", "true", "yes", "y")

                        max_denied = int(os.getenv("AIPLAT_POLICY_DENIED_MAX_AUTO_RETRY", "3") or "3")

                        meta0 = getattr(result, "metadata", {}) or {}

                        approval_id = meta0.get("approval_request_id")

                        reason = str(meta0.get("reason") or meta0.get("error_code") or "policy_denied")

                        result_output = (

                            "POLICY_DENIED: tool call rejected by policy.\n"

                            f"- tool: {tool_name}\n"

                            f"- reason: {reason}\n"

                            + (f"- approval_request_id: {approval_id}\n" if approval_id else "")

                            + "\nOptional retry strategies (choose one):\n"

                            "1) Switch to safer read-only tools (Read/Grep/Glob) to gather info first.\n"

                            "2) Narrow the scope / adjust params (e.g. read a single file, avoid write/execute).\n"

                            "3) Search tools via tool_search: {\"tool\":\"tool_search\",\"args\":{\"query\":\"read\"}}.\n"

                            "4) If a high-risk operation is truly needed, go through the approval flow (if approval_request_id is returned).\n"

                        )

                        if (not auto_retry) or denied_count >= max_denied:

                            state.metadata["pause_requested"] = True

                        ok = False

                    else:

                        result_output = result.output if hasattr(result, 'output') else str(result)

                        ok = bool(getattr(result, "success", True))

                        if not ok:

                            # P0-2: surface structured error diagnostics so the LLM can

                            # reason about self-healing (Hermes Layer 2), not just see a

                            # bare error string.

                            diag = []

                            etype = getattr(result, "error_type", None)

                            ecode = getattr(result, "exit_code", None)

                            estderr = getattr(result, "stderr", None)

                            ehint = getattr(result, "recovery_hint", None)

                            if etype:

                                diag.append(f"error_type={etype}")

                            if ecode is not None:

                                diag.append(f"exit_code={ecode}")

                            if estderr:

                                diag.append(f"stderr={str(estderr)[:300]}")

                            if ehint:

                                diag.append(f"recovery_hint={ehint}")

                            if diag:

                                result_output = f"{result_output}\n[DIAGNOSTICS] " + " | ".join(diag)

                except Exception as e:

                    result_output = f"Tool error: {e}"

                    ok = False

                try:

                    if getattr(result, "error", None) == "approval_required":

                        st = "approval_required"

                    elif getattr(result, "error", None) == "policy_denied":

                        st = "policy_denied"

                    else:

                        st = "success" if ok else "failed"

                    await self._emit_routing_explain(state, routing_decision_id, "tool", str(tool_name), top, st, str(getattr(result, "error", "") or ""))

                except Exception as e:

                    logging.warning(str(e), exc_info=True)

                state.metadata["tool_calls"] = int(state.metadata.get("tool_calls", 0) or 0) + 1

                if not ok:

                    state.metadata["tool_failures"] = int(state.metadata.get("tool_failures", 0) or 0) + 1

                await self._trigger_hook(HookPhase.POST_TOOL_USE, {"tool_name": tool_name, "result": result_output, "format": parsed.format})

                await self._trigger_hook(HookPhase.POST_APPROVAL_CHECK, {"tool_name": tool_name, "allowed": True})

                # Encode tool call as structured message in trajectory

                tool_use_id = uuid.uuid4().hex

                msg_list = state.context.setdefault("messages", [])

                msg_list.append({"role": "assistant", "content": json.dumps({

                    "type": "tool_use", "id": tool_use_id, "name": str(tool_name),

                    "input": str(tool_args)[:500] if tool_args else {},

                }, ensure_ascii=False)})



                raw_output = str(result_output)

                if len(raw_output) <= 2000:

                    display_output = raw_output

                else:

                    head = raw_output[:1000]

                    tail = raw_output[-1000:] if len(raw_output) > 1000 else ""

                    display_output = (

                        f"[Tool Result: {tool_name} ({tool_use_id})\n"

                        f"First 1K: {head}\n"

                        f"-- content too long ({len(raw_output)} chars), truncated --\n"

                        f"Last 1K: {tail}\n"

                        f"summary generating... use sys_read_scratchpad({tool_use_id}) to get the full smart summary]"

                    )

                    scratchpad = state.context.setdefault("_scratchpad", {})

                    asyncio.create_task(

                        _background_tool_summarize(tool_use_id, str(tool_name), raw_output, scratchpad)

                    )



                msg_list.append({"role": "user", "content": json.dumps({

                    "type": "tool_result", "tool_use_id": tool_use_id, "name": str(tool_name),

                    "success": ok, "output": display_output,

                }, ensure_ascii=False)})

                return str(result_output)

        # ---- MCP lazy-load: try on-demand discovery before giving up ----

        try:

            from core.harness.integration import get_mcp_runtime, get_tool_registry

            rt = get_mcp_runtime()

            if hasattr(rt, '_registered') and rt._registered:

                tr = get_tool_registry()

                found = await rt.search_and_register(str(tool_name), tr)

                if found:

                    for tool in self._tools:

                        if str(getattr(tool, 'name', '')).strip().lower() == str(found).strip().lower():

                            result = await sys_tool_call(

                                tool, tool_args,

                                user_id=state.context.get("user_id", "system"),

                                session_id=state.context.get("session_id", "default"),

                                trace_context={

                                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                                },

                            )

                            state.metadata["tool_calls"] = int(state.metadata.get("tool_calls", 0) or 0) + 1

                            return getattr(result, 'output', str(result)) if hasattr(result, 'output') else str(result)

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        # ---- File/Code syscall fallback ----

        file_result = await self._try_file_syscall(tool_name, tool_args, state)

        if file_result is not None:

            return str(file_result)

        return f"Tool not found: {tool_name}"



    async def _act(self, state: LoopState) -> str:

        """Acting phase — execute tool or skill (thin orchestrator, P1-6)."""

        reasoning = state.context.get("reasoning", "")

        parsed = parse_action_call(reasoning)

        routing_decision_id = self._init_routing_id(state)

        if not parsed:

            await self._emit_no_action(state, routing_decision_id)

            return "No action to execute"

        self._iters_since_skill += 1

        self._iters_since_memory += 1

        state.context["_capability_attempted"] = True

        if parsed.kind == "skill":

            # skill_delivery=once: do not re-invoke the same primary skill after success

            delivered = str(state.context.get("_primary_skill_delivered") or "").strip().lower()

            want = str(getattr(parsed, "name", "") or "").strip().lower()

            mode = str(state.context.get("_skill_delivery") or "").strip().lower()

            if mode == "once" and delivered and want and delivered == want:

                prev = state.context.get("_primary_skill_output")

                nxt = self._pending_coding_followup(state)
                if nxt:
                    steer = (
                        f"Do NOT call it again. Next call skill `{nxt}` "
                        f"(type=skill_call), then DONE."
                    )
                else:
                    steer = (
                        "Do NOT call it again. Output DONE / {\"type\":\"done\"} "
                        "with the prior result."
                    )

                return (

                    f"[skill_delivery=once] Skill `{parsed.name}` already delivered. "

                    f"{steer}\n\n"

                    f"""{str(prev or '')[:8000]}"""

                )

            return await self._dispatch_skill_call(state, parsed, routing_decision_id)

        return await self._dispatch_tool_call(state, parsed, routing_decision_id)

    async def _observe(self, state: LoopState) -> str:

        """Observing phase"""

        result = state.context.get("action_result", "")

        try:

            from core.services.execution_store import get_execution_store

            store = get_execution_store()

            await store.add_syscall_event({

                "id": f"{state.context.get('_run_id','?')}:observe:{state.step_count}",

                "span_id": f"observe:{state.context.get('_agent_id','react')}:{state.step_count}",

                "parent_span_id": state.context.get("_current_step_span_id"),

                "kind": "observe", "name": "observation", "status": "ok" if result else "empty",

                "run_id": state.context.get("_run_id") or "",

                "start_time": time.time(),

                "result": {"summary": str(result)[:500]},

                "step_number": state.step_count,

            })

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # §Skill 4: Inline self-correction — let Agent critique its own output

        corrected = await self._try_self_correct(result, state)

        if corrected:

            state.context["action_result"] = corrected

            result = corrected



        return result



    async def _try_self_correct(self, result: str, state: LoopState) -> str:

        """PostObserve: Agent self-critique → auto-fix if issues found.



        Uses prompt_loader templates reflection-critic + reflection-improve.

        Controlled by AIPLAT_SELF_CORRECT_ENABLED (default: true).

        Max 1 correction attempt per step to prevent infinite loops.

        Never run on Skill/tool failures — a second LLM here wedges the loop
        after architecture_lone_api rejects (run-467095c8289b: observe ok,
        then hung in self-correct with no step_2).

        Also skip after a successful skill_call: the skill body is the product
        (test_executor run-74a19d55326c: observation 7ms then step_1 stuck 419s
        in nested critic with no step_2 / no auto_done).

        """

        import asyncio as _aio_sc
        import os as _os

        enabled = _os.getenv("AIPLAT_SELF_CORRECT_ENABLED", "true")

        if enabled in ("0", "false", "no") or not result:

            return ""

        if state.context.get("skill_call") or state.context.get("_primary_skill_delivered"):
            return ""

        text = str(result)
        head = text.lstrip()[:240].lower()
        # Failed skill/tool observations must go back to ReAct reason, not a
        # nested critic LLM that can starve local_llm_inflight / status API.
        if (
            head.startswith("skill error:")
            or head.startswith("denied:")
            or head.startswith("policy_denied")
            or "architecture_lone_api" in head
            or "lone_api_rejected" in head
            or "rejected output (do not treat as final answer)" in head
        ):
            return ""

        correction_count = state.context.get("_correction_count", 0)

        if correction_count >= 1:

            return ""

        # Hard cap so a wedged critic cannot leave the agent row running forever.
        try:
            sc_timeout = float(_os.getenv("AIPLAT_SELF_CORRECT_TIMEOUT_SECONDS", "45") or "45")
        except ValueError:
            sc_timeout = 45.0

        async def _critique_and_improve() -> str:
            from core.harness.utils.prompt_loader import _sync_resolve

            critique_prompt = _sync_resolve(
                "reflection-critic",
                output=text[:2000],
                dimensions="correctness, completeness, logical consistency, format compliance",
            )
            critique = await sys_llm_generate(
                None,
                [{"role": "user", "content": critique_prompt}],
                model_name=state.context.get("model", ""),
                max_tokens=4000,
            )
            critique_text = critique.content if hasattr(critique, "content") else str(critique)
            if not critique_text or len(critique_text) < 20:
                return ""

            import json as _json

            verdict = "PASS"
            try:
                parsed = _json.loads(critique_text) if critique_text.strip().startswith("{") else {}
                verdict = parsed.get("verdict", "PASS")
            except Exception:
                verdict = "PASS"  # Non-JSON response → don't correct

            if verdict == "PASS":
                return ""

            improve_prompt = _sync_resolve(
                "reflection-improve",
                previous_output=text[:1500],
                feedback=critique_text[:1000],
            )
            improved = await sys_llm_generate(
                None,
                [{"role": "user", "content": improve_prompt}],
                model_name=state.context.get("model", ""),
                max_tokens=4000,
            )
            improved_text = improved.content if hasattr(improved, "content") else str(improved)
            if improved_text and len(improved_text) > 20:
                state.context["_correction_count"] = correction_count + 1
                state.context["_was_corrected"] = True
                logging.getLogger("loop.correct").info(
                    "Self-correction applied at step %d via reflection templates",
                    state.step_count,
                )
                return improved_text
            return ""

        try:
            return await _aio_sc.wait_for(_critique_and_improve(), timeout=sc_timeout)
        except _aio_sc.TimeoutError:
            logging.getLogger("loop.correct").warning(
                "Self-correction timed out after %.0fs — skipping (run_id=%s)",
                sc_timeout,
                state.context.get("_run_id"),
            )
        except Exception:
            logging.getLogger("loop.correct").debug("Self-correction skipped", exc_info=True)

        return ""





class PlanExecuteLoop(BaseLoop):

    """

    Plan-Execute Loop

    

    Implements two-phase execution:

    - Plan: Analyze task and create execution plan

    - Execute: Execute plan steps using available tools/skills

    """



    def __init__(

        self,

        config: Optional[LoopConfig] = None,

        hook_manager: Optional[HookManager] = None,

        model: Optional[Any] = None,

        skills: Optional[List[Any]] = None,

        tools: Optional[List[Any]] = None

    ):

        super().__init__(config, hook_manager)

        self._model = model

        self._skills = skills or []

        self._tools = tools or []

        self._plan_steps: List[Dict[str, Any]] = []

        self._current_node = "plan"



    def set_model(self, model: Any) -> None:

        self._model = model



    def set_skills(self, skills: List[Any]) -> None:

        self._skills = skills



    def set_tools(self, tools: List[Any]) -> None:

        self._tools = tools



    async def step(self, state: LoopState) -> LoopState:

        """Execute Plan-Execute step"""

        state.step_count += 1

        

        if self._current_node == "plan":

            state = await self._plan(state)

        elif self._current_node == "execute":

            state = await self._execute(state)

        

        state.history.append({

            "step": state.step_count,

            "node": self._current_node,

            "state": state.current.value

        })

        

        return state



    async def _plan(self, state: LoopState) -> LoopState:

        """Planning phase - create execution plan"""

        state.current = LoopStateEnum.REASONING

        

        if self._model:

            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true").lower() in ("1", "true", "yes", "y"):

                prompt = PromptAssembler().build_plan_execute_plan_messages(task=state.context.get("task", ""))

            else:

                from core.harness.utils.prompt_loader import _sync_resolve
                prompt = _sync_resolve("plan-execute-plan", task=state.context.get("task", ""))

            response = await sys_llm_generate(

                self._model,

                prompt,

                                trace_context={

                                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                                    "parent_span_id": state.context.get("_current_step_span_id"),

                                },

            )

            try:

                usage = getattr(response, "usage", None)

                if isinstance(usage, dict):

                    total = usage.get("total_tokens")

                    if total is None:

                        total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)

                    state.used_tokens = float(getattr(state, "used_tokens", 0) or 0) + float(total or 0)

            except Exception as e:

                logging.warning(str(e), exc_info=True)

            

            # Parse plan (simplified)

            self._plan_steps = [

                {"step": i + 1, "action": line.strip().lstrip("0123456789. ").strip()}

                for i, line in enumerate(response.content.split("\n"))

                if line.strip() and not line.strip().startswith("#")

            ]

        

        state.context["plan"] = self._plan_steps

        self._current_node = "execute"

        state.current = LoopStateEnum.ACTING

        

        return state



    async def _execute(self, state: LoopState) -> LoopState:

        """Execution phase - execute plan steps with tool/skill support"""

        state.current = LoopStateEnum.ACTING

        

        current_step = state.context.get("current_step", 0)

        

        if current_step < len(self._plan_steps):

            step = self._plan_steps[current_step]

            action = step.get("action", "")

            state.context["current_step"] = current_step + 1

            

            # Pre-acting hook

            await self._trigger_hook(HookPhase.PRE_ACT, {"state": state, "step": step})

            

            step_result = None

            

            # Execute only when explicitly routed (avoid substring accidental dispatch)

            parsed_action = parse_action_call(action)

            if parsed_action and parsed_action.kind == "tool" and self._tools:

                for tool in self._tools:

                    tool_name = getattr(tool, "name", "")

                    if str(tool_name).strip().lower() == str(parsed_action.name).strip().lower():

                        try:

                            await self._trigger_hook(HookPhase.PRE_TOOL_USE, {"tool": tool_name, "tool_args": parsed_action.args, "format": parsed_action.format})

                            result = await sys_tool_call(

                                tool,

                                parsed_action.args,

                                user_id=state.context.get("user_id", "system"),

                                session_id=state.context.get("session_id", "default"),

                                trace_context={

                                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                                },

                            )

                            step_result = result.output if hasattr(result, "output") else str(result)

                            await self._trigger_hook(HookPhase.POST_TOOL_USE, {"tool": tool_name, "result": step_result, "format": parsed_action.format})

                            break

                        except Exception as e:

                            step_result = f"Tool error ({tool_name}): {e}"



            if step_result is None and parsed_action and parsed_action.kind == "skill" and self._skills:

                for skill in self._skills:

                    skill_name = getattr(skill, "_config", None)

                    skill_name = skill_name.name if skill_name else getattr(skill, "name", "")

                    if str(skill_name).strip().lower() == str(parsed_action.name).strip().lower():

                        try:

                            from ...harness.interfaces import SkillContext

                            skill_context = SkillContext(

                                session_id=state.context.get("session_id", "loop"),

                                user_id=state.context.get("user_id", "system"),

                                variables=parsed_action.args,

                                tools=[t.name for t in self._tools if hasattr(t, "name")],

                            )

                            skill_call_args = dict(parsed_action.args) if isinstance(parsed_action.args, dict) else {}
                            skill_call_args = self._inject_user_task_into_skill_args(state, skill_call_args)
                            skill_call_args = self._inject_preferred_language_into_skill_args(
                                state, str(skill_name or ""), skill_call_args
                            )
                            from core.harness.utils.execute_session import resolve_bound_skill_ids
                            bound_ids = resolve_bound_skill_ids(state, self._skills)
                            if bound_ids:
                                skill_call_args["_bound_skill_ids"] = list(bound_ids)
                            skill_context.variables = skill_call_args

                            await self._trigger_hook(HookPhase.PRE_SKILL_USE, {"skill": skill_name, "skill_args": skill_call_args, "format": parsed_action.format})

                            result = await sys_skill_call(

                                skill,

                                skill_call_args,

                                context=skill_context,

                                user_id=skill_context.user_id,

                                session_id=skill_context.session_id,

                                trace_context={

                                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                                    "parent_span_id": state.context.get("_current_step_span_id"),

                                    "_bound_skill_ids": list(bound_ids),

                                },

                            )

                            step_result = result.output if hasattr(result, "output") else str(result)

                            await self._trigger_hook(HookPhase.POST_SKILL_USE, {"skill": skill_name, "result": step_result, "format": parsed_action.format})

                            break

                        except Exception as e:

                            step_result = f"Skill error ({skill_name}): {e}"

            

            # Fall back to model for this step

            if step_result is None and self._model:

                try:

                    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true").lower() in ("1", "true", "yes", "y"):

                        prompt = PromptAssembler().build_plan_execute_step_messages(

                            action=action,

                            task=state.context.get("task", ""),

                        )

                    else:

                        prompt = f"Execute this step: {action}\nContext: {state.context.get('task', '')}"

                    response = await sys_llm_generate(

                        self._model,

                        prompt,

                                trace_context={

                                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),

                                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),

                                    "parent_span_id": state.context.get("_current_step_span_id"),

                                },

                    )

                    step_result = response.content

                except Exception as e:

                    step_result = f"Model error: {e}"

            

            if step_result is None:

                step_result = f"No handler for step: {action}"

            

            state.context[f"step_{current_step}_result"] = step_result

            state.context["action_result"] = step_result

            

            # Post-acting hook

            await self._trigger_hook(HookPhase.POST_ACT, {"state": state, "result": step_result})

            

            if current_step + 1 >= len(self._plan_steps):

                state.context["output"] = state.context.get("step_0_result", step_result)

                try:
                    from core.harness.utils.execute_session import (
                        finalize_agent_after_skill_delivery,
                    )
                    await finalize_agent_after_skill_delivery(
                        run_id=str(state.context.get("_run_id") or state.context.get("run_id") or ""),
                        agent_id=str(state.context.get("_agent_id") or ""),
                        output_text=str(state.context.get("output") or step_result or ""),
                        trace_id=str(state.context.get("_trace_id") or state.context.get("trace_id") or ""),
                        metadata_extra={"finalize_source": "plan_execute_finish"},
                    )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "plan_execute finalize skipped", exc_info=True
                    )

                state.current = LoopStateEnum.FINISHED

                self._current_node = "finish"

        else:

            try:
                from core.harness.utils.execute_session import (
                    finalize_agent_after_skill_delivery,
                )
                await finalize_agent_after_skill_delivery(
                    run_id=str(state.context.get("_run_id") or state.context.get("run_id") or ""),
                    agent_id=str(state.context.get("_agent_id") or ""),
                    output_text=str(state.context.get("output") or ""),
                    trace_id=str(state.context.get("_trace_id") or state.context.get("trace_id") or ""),
                    metadata_extra={"finalize_source": "plan_execute_empty_plan"},
                )
            except Exception:
                logging.getLogger(__name__).debug(
                    "plan_execute empty finalize skipped", exc_info=True
                )

            state.current = LoopStateEnum.FINISHED

            self._current_node = "finish"

        

        return state





def create_loop(

    loop_type: str = "react",

    config: Optional[LoopConfig] = None,

    **kwargs

) -> ILoop:

    """

    Factory function to create execution loop

    

    Args:

        loop_type: Type of loop ("react", "plan_execute")

        config: Loop configuration

        **kwargs: Additional arguments

        

    Returns:

        ILoop: Execution loop instance

    """

    if loop_type == "react":

        return ReActLoop(config=config, **kwargs)

    elif loop_type == "plan_execute":

        return PlanExecuteLoop(config=config, **kwargs)

    else:

        return BaseLoop(config=config)

