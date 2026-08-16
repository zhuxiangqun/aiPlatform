"""

Execution Loop — Base Implementation.



Provides BaseLoop (generic loop infrastructure) and shared helpers.

"""

from abc import ABC, abstractmethod

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional, Callable, Tuple

import asyncio

import json

import os

import time

import re

import uuid

import logging



from core.harness.memory.compression import _background_tool_summarize



from ...interfaces.loop import (

    ILoop,

    LoopState,

    LoopStateEnum,

    LoopConfig,

    LoopResult,

)

from ...infrastructure.hooks import HookManager, HookPhase, HookContext

from ..tool_calling import parse_action_call, parse_tool_call

from ...syscalls import sys_llm_generate, sys_skill_call, sys_tool_call

from ...assembly import PromptAssembler, ContextAssembler, ContextSource

from ...kernel.runtime import get_kernel_runtime



def _infer_task_type(task: str, agent_id: str) -> str:

    """Infer the task source type (Paper Data Recipes: coding/terminal/qa/system)"""

    t = (task or "").lower(); a = (agent_id or "").lower()

    if any(kw in a for kw in ("terminal", "shell", "bash", "cmd", "console")): return "terminal"

    if any(kw in t for kw in ("$", "ls ", "cd ", "grep", "git ", "pwd", "chmod")): return "terminal"

    if any(kw in a for kw in ("code", "coder", "programmer", "dev", "engineer")): return "coding"

    if any(kw in t for kw in ("def ", "class ", "import ", "function", "test_")): return "coding"

    if any(kw in a for kw in ("search", "retrieval", "qa", "question", "answer")): return "qa"

    if any(kw in t for kw in ("search", "find ", "query ", "retrieve")): return "qa"

    return "general"





class BaseLoop(ILoop):

    """

    Base execution loop implementation

    

    Provides common functionality for execution loops.

    """



    def __init__(

        self,

        config: Optional[LoopConfig] = None,

        hook_manager: Optional[HookManager] = None

    ):

        self._config = config or LoopConfig()

        self._hook_manager = hook_manager or HookManager()

        self._current_state = LoopState()

        self._current_node = "init"

        self._step_handlers: Dict[LoopStateEnum, Callable] = {}



    async def run(self, state: LoopState, config: LoopConfig) -> LoopResult:

        """Run execution loop"""

        self._current_state = state

        self._config = config

        stop_reason = None



        # Session start + pre-loop hooks

        await self._trigger_hook(HookPhase.SESSION_START, {"state": state, "config": config})

        await self._trigger_hook(HookPhase.PRE_LOOP, {"state": state})



        # Paper "Data Recipes for Agentic Models": task source classification

        task = str(state.context.get("task") or "")

        agent_id = str(state.context.get("_agent_id") or state.context.get("agent_id") or "")

        task_type = _infer_task_type(task, agent_id)

        state.context["task_type"] = task_type



        # Target continuity: detect if user input is continuation of prior task

        # or a new task (Agent runtime deterministic constraint — layer 4 — Hermes inspired)

        try:

            if os.getenv("AIPLAT_CONTINUITY_ENABLED", "true").lower() not in ("0", "false", "no"):

                last_task = str(state.context.get("_last_task") or "")

                if last_task and task and last_task != task:

                    from core.harness.execution.loop.target_continuity import TargetContinuity

                    continuity = TargetContinuity().decide(last_task, task)

                    state.context["_continuity"] = continuity

                    if not continuity["same_task"]:

                        state.context["_continuity_new_task"] = True

                state.context["_last_task"] = task

        except Exception:

            logging.getLogger(__name__).debug('run failed', exc_info=True)


        # v2.9: GrillingGate — auto-detect ambiguous input before reasoning

        # Triggers grilling interview when user input is too short/vague,

        # then injects clarified context into system prompt downstream.

        if os.getenv("AIPLAT_AUTO_GRILLING_ENABLED", "true").lower() not in ("0", "false", "no"):

            try:

                await self._auto_grill_if_ambiguous(state, task, agent_id)

            except Exception:

                logging.getLogger(__name__).debug('run failed', exc_info=True)
        

        # PraxisRecorder — session-level execution recording

        try:

            from core.harness.practice.recorder import PraxisRecorder

            run_id = getattr(state, "context", {}).get("_run_id", "") or ""

            agent_id = getattr(state, "context", {}).get("_agent_id", "") or ""

            recorder = PraxisRecorder(session_id=run_id, run_id=run_id, agent_id=agent_id)

            recorder.start()

            self._praxis_recorder = recorder

        except Exception:

            self._praxis_recorder = None

        

        try:

            while self.should_continue(self._current_state):

                # Contract check (optional hooks may block)

                contract_results = await self._trigger_hook(

                    HookPhase.PRE_CONTRACT_CHECK,

                    {"state": self._current_state, "config": config},

                )

                deny = _extract_deny(contract_results)

                if deny:

                    await self._trigger_hook(HookPhase.SCOPE_REVIEW, {"reason": deny.get("reason", "contract denied")})

                    raise RuntimeError(deny.get("reason", "contract denied"))



                # Execute step

                self._current_state = await self.step(self._current_state)



                # Emit step_end so ExecutionViewer can mark step as completed

                try:

                    from core.services.execution_store import get_execution_store

                    store = get_execution_store()

                    step_num = self._current_state.step_count

                    agent_id = self._current_state.context.get("_agent_id") or "react"

                    step_span_id = f"step:{agent_id}:{step_num}"

                    end_ts = time.time()

                    await store.add_syscall_event({

                        "id": f"{self._current_state.context.get('_run_id','?')}:step_end:{step_num}",

                        "span_id": step_span_id,

                        "parent_span_id": f"agent:{agent_id}:start",

                        "kind": "step", "name": f"step_{step_num}", "status": self._current_state.current.value,

                        "run_id": self._current_state.context.get("_run_id") or "",

                        "start_time": end_ts,

                        "duration_ms": 0,

                        "args": {

                            "reasoning": str(self._current_state.context.get("reasoning", ""))[:200],

                            "action_result": str(self._current_state.context.get("action_result", ""))[:200],

                        },

                        "step_number": step_num,

                    })

                except Exception as e:

                    logging.warning(str(e), exc_info=True)



                await self._trigger_hook(

                    HookPhase.POST_CONTRACT_CHECK,

                    {"state": self._current_state, "config": config},

                )



                # Observability-driven control (minimal closed-loop)

                self._apply_observability_control(self._current_state, config)

                if self._current_state.current == LoopStateEnum.PAUSED:

                    stop_reason = "paused"

                    break

                

                # Check for errors

                if self._current_state.current == LoopStateEnum.ERROR:

                    if config.stop_on_error:

                        break

            

            # Determine stop reason

            if self._current_state.current == LoopStateEnum.FINISHED:

                stop_reason = "finished"

            elif self._current_state.current == LoopStateEnum.ERROR:

                stop_reason = "error"

            elif self._current_state.step_count >= self._config.max_steps:

                stop_reason = "max_steps"

            elif self._current_state.budget_remaining <= 0:

                stop_reason = "budget_exhausted"

            else:

                stop_reason = "stopped"



            # Persist stop_reason for observability (MUST be in output event)

            self._current_state.context["_stop_reason"] = stop_reason



            # Save Praxis recording for replay

            if hasattr(self, '_praxis_recorder') and self._praxis_recorder:

                try:

                    session = self._praxis_recorder.finish(stop_reason or "unknown")

                    from core.services.execution_store import get_execution_store

                    store = get_execution_store()

                    await store.upsert_global_setting(

                        key=f"praxis:{session.run_id}",

                        value={"session": session.to_dict()},

                    )

                except Exception as e:

                    logging.warning(str(e), exc_info=True)



            # Post-loop hook

            await self._trigger_hook(HookPhase.POST_LOOP, {"state": self._current_state})

            await self._trigger_hook(HookPhase.STOP, {"state": self._current_state, "reason": stop_reason})

            await self._trigger_hook(HookPhase.SESSION_END, {"state": self._current_state, "reason": stop_reason})

            

            error = None

            if self._current_state.current == LoopStateEnum.PAUSED:

                error = self._current_state.context.get("error") or "paused"

            elif self._current_state.current == LoopStateEnum.ERROR:

                error = self._current_state.context.get("error") or "error"



            # Fire-and-forget: auto-score this run with the 6-dim evaluator so the

            # Agent Evaluation dashboard reflects real runtime quality (P0-2).

            try:

                import asyncio as _asyncio_sc

                _asyncio_sc.ensure_future(self._try_auto_score_run(self._current_state, stop_reason))

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)


            return LoopResult(

                success=self._current_state.current == LoopStateEnum.FINISHED,

                final_state=self._current_state,

                output=self._current_state.context.get("output"),

                error=error,

                metadata={"steps": self._current_state.step_count, "stop_reason": stop_reason}

            )

            

        except Exception as e:

            self._current_state.current = LoopStateEnum.ERROR

            stop_reason = stop_reason or "exception"

            try:

                await self._trigger_hook(HookPhase.STOP, {"state": self._current_state, "reason": stop_reason, "error": str(e)})

                await self._trigger_hook(HookPhase.SESSION_END, {"state": self._current_state, "reason": stop_reason, "error": str(e)})

            except Exception as e:

                logging.warning(str(e), exc_info=True)

            # Fire-and-forget: trigger AutoLearner on unhandled exceptions

            try:

                import asyncio as _asyncio2

                _asyncio2.ensure_future(self._try_trigger_auto_learner_from_exception(

                    state=self._current_state, exc=e, stop_reason=stop_reason

                ))

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)
            return LoopResult(

                success=False,

                final_state=self._current_state,

                error=str(e),

                metadata={"exception": type(e).__name__}

            )



    async def _auto_grill_if_ambiguous(self, state: LoopState, task: str, agent_id: str) -> None:

        """GrillingGate: auto-detect ambiguous user input and inject clarified context.



        Evaluates runtime conditions — not agent declarations — to decide whether

        to trigger a GrillingBridge interview. Injects clarified output as a 

        user-role message appended to the conversation so downstream reasoning

        benefits from the structured requirements.



        Conditions for triggering:

        - Task text is short (< 30 chars) and contains grilling-trigger keywords

        - OR task lacks concrete parameters (no numbers, no file paths, no JSON)

        - AND we haven't already grilled in this context

        - AND this is an interactive session (not batch/automated)



        Gate: AIPLAT_AUTO_GRILLING_ENABLED=true (default). Set to false to disable.

        """

        import re, os as _os



        # Guard: don't grill if already did in this context

        if state.context.get("_auto_grilled"):

            return

        state.context["_auto_grilled"] = True



        # Guard: only in interactive sessions (has human user)

        is_interactive = state.context.get("_is_interactive", True)

        if not is_interactive:

            return



        # Check ambiguity: short input with grilling trigger keywords

        task_str = str(task or "").strip()

        if not task_str:

            return



        from core.harness.utils.zh_language import TRIGGER_KEYWORDS

        trigger_keywords = TRIGGER_KEYWORDS

        is_short = len(task_str) < 30

        has_trigger = any(kw in task_str for kw in trigger_keywords)

        has_concrete_params = bool(re.search(r'\d+', task_str)) or '{"' in task_str or '/' in task_str



        if not ((is_short and has_trigger) or (not has_concrete_params and len(task_str) < 100)):

            return



        # Determine domain from agent context

        domain_id = state.context.get("_domain_id") or state.context.get("domain_id") or ""

        entry_point = "agent_chat"

        if state.context.get("_pipeline_stage"):

            entry_point = "pipeline_hitl"

        elif state.context.get("_entry_point"):

            entry_point = state.context["_entry_point"]



        try:

            from core.api.core_facade import start_grilling, continue_grilling, _finalize_grilling



            # Start grilling session

            ctx = {"task": task_str, "agent_id": agent_id}

            r = start_grilling(entry_point, domain_id, ctx)

            if r["status"] != "asking":

                return



            session_id = r["session_id"]



            # Collect answers (max 5 rounds, fire-and-forget style — use quick defaults)

            for _round in range(5):

                q = r.get("question", {})

                options = q.get("options", [])

                if options:

                    # Auto-pick first option for speed (user can refine later via manual GrillPanel)

                    answer = options[0]

                else:

                    from core.harness.utils.zh_language import PROACTIVE_GOAL_NEGATIVE_ANSWER
                    answer = PROACTIVE_GOAL_NEGATIVE_ANSWER

                r = continue_grilling(session_id, answer)

                if r["status"] == "completed":

                    break



            if r["status"] != "completed":

                return



            # Inject clarified summary into context

            summary = r.get("summary_markdown", "")

            answers_flat = r.get("answers_flat", {})

            if summary or answers_flat:

                clarifications = []

                if summary:

                    clarifications.append(summary)

                if answers_flat:

                    clarifications.append("\n## Key decisions")

                    for k, v in answers_flat.items():

                        clarifications.append(f"- **{k}**: {v}")

                clarified_text = "\n".join(clarifications)



                # Append as user-role message so LLM treats it as part of the task

                state.context["_grilling_output"] = clarified_text[:2000]

                state.context["_grilling_dimensions"] = str(answers_flat)



                import logging

                logging.getLogger("loop.grilling").info(

                    "auto-grilled %s (%s) → %d dimensions clarified",

                    agent_id[:30], task_str[:40], len(answers_flat))

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        """Score a completed production run with the 6-dimension EvalMetricsEngine

        and persist it, so Agent Evaluation reflects real runtime quality without

        manual eval sets (P0-2). Fire-and-forget — never raises into the loop.



        Skips internal/eval/autoreview runs to avoid noise and recursion. All 5

        behavioural dimensions (tool/step/error/safety/cost) come from the run's

        real syscall_events; task_completion comes from the final loop state.

        """

        try:

            import os

            if os.getenv("AIPLAT_AUTO_SCORE_ENABLED", "true").lower() in ("0", "false", "no"):

                return

            ctx = state.context or {}

            agent_id = str(ctx.get("_agent_id") or ctx.get("agent_id") or "").strip()

            run_id = str(ctx.get("_run_id") or ctx.get("run_id") or "").strip()

            if not agent_id or not run_id:

                return

            # Recursion/noise guard: skip eval + autoreview + internal runs

            if run_id.startswith(("eval-", "auto-")):

                return

            if str(ctx.get("_active_skill") or "") == "autoreview":

                return



            from core.services.execution_store import get_execution_store

            store = get_execution_store()

            events = await store.list_syscall_events(run_id=run_id, limit=200)

            if not events:

                return



            from core.harness.evaluation.eval_types import SingleTaskResult, TaskResultLevel

            from core.harness.evaluation.eval_metrics import EvalMetricsEngine

            from core.harness.evaluation.eval_runner import serialize_eval_result, persist_runtime_eval



            cur = getattr(state.current, "value", str(state.current))

            level = (

                TaskResultLevel.COMPLETE if cur == "finished"

                else TaskResultLevel.CORRECT_FAILURE if cur == "paused"

                else TaskResultLevel.ERROR_FAILURE

            )

            output = str(ctx.get("output") or "")

            tr = SingleTaskResult(

                task_id=run_id, agent_id=agent_id, run_id=run_id, level=level,

                reasoning=f"auto-runtime:{stop_reason}", evidence=output[:500],

                steps=int(getattr(state, "step_count", 0) or 0),

            )

            result = EvalMetricsEngine().compute_all(

                agent_id=agent_id, task_results=[tr], syscall_events=events,

                eval_set_id="auto-runtime",

            )

            keep = int(os.getenv("AIPLAT_AUTO_SCORE_KEEP", "50"))

            persist_runtime_eval(agent_id, serialize_eval_result(result), keep=keep)

        except Exception as e:

            logging.debug("auto-score skipped: %s", e)



    def should_continue(self, state: LoopState) -> bool:

        """Determine if loop should continue"""

        # Hard safety cap: prevent runaway loops regardless of config

        if state.step_count >= 1000:

            logging.getLogger("aiplat.loop").error(

                "SAFETY STOP: loop exceeded 1000 steps (run_id=%s, agent=%s, steps=%d)",

                state.context.get("_run_id", "?"),

                state.context.get("agent_id", "?"),

                state.step_count,

            )

            return False

        

        # Check max steps

        if state.step_count >= self._config.max_steps:

            return False

        

        # Check token budget

        if state.budget_remaining <= 0:

            return False

        

        # Check state

        if state.current in [LoopStateEnum.FINISHED, LoopStateEnum.ERROR, LoopStateEnum.PAUSED]:

            return False

        

        return True



    def _apply_observability_control(self, state: LoopState, config: LoopConfig) -> None:

        """

        Minimal observability-driven control:

        - If tool_error_rate > 0.2 and tool_calls >= 10 -> pause + require manual

        - If token usage ratio > 0.8 -> compact messages (keep last 2)

        """

        # 1) tool error rate based pause

        tool_calls = int(state.metadata.get("tool_calls", 0) or 0)

        tool_failures = int(state.metadata.get("tool_failures", 0) or 0)

        if tool_calls >= 10:

            rate = tool_failures / max(1, tool_calls)

            if rate > 0.2:

                state.current = LoopStateEnum.PAUSED

                state.metadata["control_action"] = "require_manual"

                state.metadata["tool_error_rate"] = rate

                state.context["observation"] = f"Paused: tool_error_rate={rate:.2f} exceeds threshold"

                return



        # 2) token budget based compaction (best-effort)

        max_tokens = float(getattr(config, "max_tokens", state.max_tokens) or state.max_tokens)

        used_tokens = float(getattr(state, "used_tokens", 0) or 0)

        if max_tokens > 0 and (used_tokens / max_tokens) > 0.8:

            # If advanced compaction is enabled, let the loop implementation handle it

            # (e.g., ReActLoop._maybe_compact_messages) rather than dropping turns here.

            if True:  # always enable 5-level compaction (has its own threshold guards)

                state.metadata["control_action"] = state.metadata.get("control_action") or "context_pressure"

                state.metadata["context_pressure"] = True

                return

            msgs = state.context.get("messages")

            if isinstance(msgs, list) and len(msgs) > 2:

                state.context["messages"] = msgs[-2:]

                state.metadata["control_action"] = "compact_context"

                state.metadata["compacted_messages"] = True



    async def step(self, state: LoopState) -> LoopState:

        """Execute single step - to be implemented by subclass"""

        state.step_count += 1

        state.history.append({

            "step": state.step_count,

            "node": self._current_node,

            "state": state.current.value

        })

        

        return state



    def get_current_node(self) -> str:

        """Get current execution node"""

        return self._current_node



    async def reset(self) -> None:

        """Reset loop to initial state"""

        self._current_state = LoopState()

        self._current_node = "init"



    async def _trigger_hook(self, phase: HookPhase, data: Dict[str, Any]) -> List[Any]:

        """Trigger hooks for a phase and return hook results."""

        context = HookContext(phase=phase, state=data)

        return await self._hook_manager.trigger(phase, context)





def _extract_deny(results: List[Any]) -> Optional[Dict[str, Any]]:

    """Extract first deny dict from hook results."""

    for r in results or []:

        if isinstance(r, dict) and r.get("allow") is False:

            return r

    return None

