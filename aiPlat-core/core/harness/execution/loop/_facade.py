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
from .graph_injector import inject_graph_context, inject_memory_reminders


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

        # Emit step_start + context_snapshot (first step only) for zero-black-box tree
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            agent_id = state.context.get("_agent_id") or "react"
            step_span_id = f"step:{agent_id}:{state.step_count}"
            state.context["_current_step_span_id"] = step_span_id
            await store.add_syscall_event({
                "id": f"{state.context.get('_run_id','?')}:step:{state.step_count}",
                "span_id": step_span_id,
                "parent_span_id": f"agent:{agent_id}:start",
                "kind": "step", "name": f"step_{state.step_count}", "status": "running",
                "run_id": state.context.get("_run_id") or "",
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
            await self._trigger_hook(HookPhase.PRE_REASONING, state.context)
            state.current = LoopStateEnum.REASONING
            reasoning = await self._reason(state)
            state.context["reasoning"] = reasoning
            await self._trigger_hook(HookPhase.POST_REASONING, state.context)
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

        # 支持“直接结束”语义：当模型给出 DONE/FINAL 且没有动作调用时，直接结束。
        # 这使得在无工具调用场景也能完成一次 agent 执行（例如 mock LLM / 纯对话）。
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
                        "result": {"answer": final_text[:500]},
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
                state.current = LoopStateEnum.FINISHED
                return state
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        # Auto-detect final output / stagnation
        parsed = parse_action_call(reasoning) if reasoning else None
        # If LLM returns text answer (no tool/skill call) → treat as final output
        if not parsed and len(str(reasoning or "").strip()) > 0:
            state.context["output"] = reasoning
            try:
                from core.services.execution_store import get_execution_store
                store = get_execution_store()
                await store.add_syscall_event({
                    "id": f"{state.context.get('_run_id','?')}:done:{state.step_count}",
                    "span_id": f"done:{state.context.get('_agent_id','react')}:{state.step_count}",
                    "parent_span_id": state.context.get("_current_step_span_id"),
                    "kind": "done", "name": "auto_done", "status": "ok",
                    "run_id": state.context.get("_run_id") or "",
                    "start_time": time.time(),
                    "result": {"answer": str(reasoning)[:500]},
                    "step_number": state.step_count,
                })
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            state.current = LoopStateEnum.FINISHED
            return state
        if parsed and parsed.kind == "none" and len(str(reasoning or "").strip()) > 200:
            state.context["output"] = reasoning
            state.current = LoopStateEnum.FINISHED
            return state
        if getattr(self, '_not_found_streak', 0) >= 3 and len(str(reasoning or "").strip()) > 20:
            state.context["output"] = reasoning
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
                state.messages.append({"role": "user", "content": hint})
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
        state.context["observation"] = observation
        state.context.setdefault("_observations", []).append(observation)
        await self._trigger_hook(HookPhase.POST_OBSERVE, state.context)

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
                state.messages.append({"role": "user", "content": intervention.hint_message})
                state.context["_howl_stall"] = intervention.details
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        if "DONE" in observation.upper() or "FINISHED" in observation.upper():
            state.current = LoopStateEnum.FINISHED

        return state

    # ── DELEGATED to state_mgr.py (extracted for SRP per §5.75) ──
    async def _persist_run_state(self, state: LoopState, *, source: str, extra: Optional[Dict[str, Any]] = None):
        """Delegate to state_mgr.persist_run_state — extracted from loop.py."""
        return await persist_run_state(state, source=source, extra=extra)
    # ── DELEGATED to state_mgr.py (extracted for SRP per §5.75) ──
    async def _apply_todo_done_markers(self, state: LoopState, text: str, *, source: str):
        """Delegate to state_mgr.apply_todo_done_markers — extracted from loop.py."""
        return await apply_todo_done_markers(state, text, source=source)
    # ── DELEGATED to inference.py (extracted for SRP per §5.75) ──
    async def _reason(self, state: LoopState):
        """Delegate to inference.reason — extracted from loop.py."""
        return await reason(state, self._model, self._config, self._skills, self._tools)
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
        return await apply_context_shaping(state, self._config)
    async def _try_save_interaction(self, state: LoopState, user_msg: str, assistant_msg: str) -> None:
        """Persist interaction to MemoryManager for cross-turn context building."""
        try:
            from core.harness.memory.manager import get_memory_manager
            ns = state.context.get("_agent_namespace", "default")
            mgr = get_memory_manager(namespace=ns)
            if mgr:
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
                from core.harness.feedback_loops.local import get_local_feedback
                fb = get_local_feedback()
                if fb:
                    fb.emit("interaction", {"user": user_msg[:500], "assistant": assistant_msg[:500], "stability": stability})
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
                pass
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        
        # Fire-and-forget: trigger self-learning if interaction indicates failure
        try:
            import asyncio as _asyncio
            _asyncio.ensure_future(self._try_trigger_auto_learner(state, user_msg, assistant_msg, stability))
        except Exception:
            pass

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
                pass
        
        # CMM + ExperienceVector: extract patterns and store experience from this run
        try:
            import asyncio as _asyncio2
            _asyncio2.ensure_future(self._try_feed_learning_pipeline(state, user_msg, assistant_msg, stability))
        except Exception:
            pass

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
            pass
        
        # ExperienceVector: store this failure for future semantic retrieval
        try:
            from core.harness.learning.experience_vector import get_experience_cache
            cache = get_experience_cache()
            summary = f"[{agent_id}] {assistant_msg[:300]}"
            await cache.store(run_id=run_id, summary=summary, label="failure")
        except Exception:
            pass

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
            pass

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
            pass
        
        # ── ExperienceVector: store this interaction ──
        try:
            from core.harness.learning.experience_vector import get_experience_cache
            cache = get_experience_cache()
            label = "failure" if stability == "low" else "success"
            summary = f"[{agent_id}] User: {user_msg[:150]} | Agent: {assistant_msg[:150]}"
            await cache.store(run_id=run_id, summary=summary, label=label)
        except Exception:
            pass

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
                pass

        # ── MetaClaw: compare success vs failure for this agent's tasks ──
        try:
            from core.harness.memory.pattern_accumulator import get_pattern_accumulator
            pa = get_pattern_accumulator()
            await pa.compare_success_failure(intent=agent_id)
        except Exception:
            pass

    async def _try_extract_user_facts(self, state: LoopState, user_msg: str) -> None:
        u"""L3: Auto-extract structured facts from user messages.

        Detects patterns like "我的预算是X", "我叫Y" and updates LearnerProfile.
        Mimics ChatGPT's "Memory updated" behavior.
        """
        import re, logging
        try:
            facts = {}
            budget_match = re.search(r'预算[是为:：]\s*(\d+)\s*万?', user_msg)
            if budget_match:
                facts["budget"] = int(budget_match.group(1))

            name_match = re.search(r'(?:我|本人)[叫是称呼为]\s*([\u4e00-\u9fa5a-zA-Z]{2,10})', user_msg)
            if name_match:
                facts["name"] = name_match.group(1)

            goal_match = re.search(r'(?:目标|想|要)[是]?\s*(.{5,50})', user_msg)
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
    # ── DELEGATED to compressor.py (extracted for SRP per §5.75) ──
    async def _maybe_compact_messages(self, state: LoopState):
        """Delegate to compressor.compact_messages — extracted from loop.py."""
        return await compact_messages(state, self._config)
    def _build_compaction_prompt(self, ids_list: list, head: list) -> str:
        """Build compaction prompt from template (§8: engine code must not contain business SOP)."""
        from core.harness.assembly.compaction_prompt import get_compaction_prompt
        history_lines = [f"{m.get('role','user')}: {m.get('content','')}" for m in head if isinstance(m, dict)]
        return get_compaction_prompt(identifiers=ids_list, history_lines=history_lines)

    def _build_tools_desc(self) -> tuple[str, Dict[str, Any]]:
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
        always_include = {"tool_search"}
        ordered = list(self._tools)
        try:
            ordered.sort(key=lambda x: (0 if getattr(x, "name", "") in always_include else 1, str(getattr(x, "name", ""))))
        except Exception:
            ordered = list(self._tools)

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

        # P1-1: 动态高亮最相关的 3 个工具（不改物理顺序，包尾追加提示）
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
            pass

        return "\n".join(lines), stats

    def _build_skills_desc(self, *, context_pressure: float | None = None) -> tuple[str, Dict[str, Any]]:
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

        # P0：统一的渐进式披露预算（基于上下文压力）
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
            is_coding = bool(meta.get("uses_code_skill"))
            if not is_coding:
                return "off"
            scope = str(state.context.get("skill_scope") or "engine").lower()
            if scope == "workspace":
                return os.getenv("AIPLAT_CODING_POLICY_PROFILE_WORKSPACE", "off").strip().lower()
            return os.getenv("AIPLAT_CODING_POLICY_PROFILE_ENGINE", "off").strip().lower()
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
                "span_id": state.context.get("_current_step_span_id"),
                "parent_span_id": state.context.get("_current_step_span_id") or "",
                "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                "tenant_id": state.context.get("tenant_id"),
                "kind": "routing", "name": "routing_decision", "status": "decision",
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
                "span_id": state.context.get("_current_step_span_id"),
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

    async def _dispatch_skill_call(
        self, state: LoopState, parsed: Any, routing_decision_id: str
    ) -> str:
        skill_name = parsed.name
        skill_args = parsed.args
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
                top = await self._emit_skill_candidates_snapshot(state, routing_decision_id, "skill", str(skill_name))
                await self._emit_routing_strict_eval(state, routing_decision_id, "skill", str(skill_name), top)
                from ...interfaces import SkillContext
                await self._trigger_hook(HookPhase.PRE_SKILL_USE, {"skill": skill_name, "skill_args": skill_args, "format": parsed.format})
                try:
                    skill_context = SkillContext(
                        session_id=state.context.get("session_id", "default"),
                        user_id=state.context.get("user_id", "system"),
                        variables=skill_args,
                    )
                    _run_id = state.context.get("_run_id")
                    if _run_id and isinstance(skill_context.variables, dict):
                        skill_context.variables["_run_id"] = _run_id
                    result = await sys_skill_call(
                        skill, skill_args, context=skill_context,
                        user_id=skill_context.user_id, session_id=skill_context.session_id,
                        trace_context={
                            "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                            "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                            "parent_span_id": state.context.get("_current_step_span_id"),
                            "tenant_id": state.context.get("tenant_id"),
                            "routing_decision_id": routing_decision_id,
                            "coding_policy_profile": prof,
                            "routing_candidates_emitted": True,
                        },
                    )
                    if getattr(result, "error", None) == "approval_required":
                        state.context["error"] = "approval_required"
                        state.context["approval"] = getattr(result, "metadata", {}) or {}
                        state.metadata["pause_requested"] = True
                        result_output = "Approval required"
                    elif getattr(result, "error", None) == "policy_denied":
                        state.context["error"] = "policy_denied"
                        state.context["policy"] = getattr(result, "metadata", {}) or {}
                        state.metadata["pause_requested"] = True
                        result_output = "POLICY_DENIED"
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
                return str(result_output)
        return f"Skill not found: {skill_name}"

    async def _dispatch_tool_call(
        self, state: LoopState, parsed: Any, routing_decision_id: str
    ) -> str:
        tool_name = parsed.name
        tool_args = parsed.args
        state.context["tool_call"] = {"tool": tool_name, "args": tool_args, "format": parsed.format}
        state.context["_coding_policy_profile"] = "off"
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
                            "POLICY_DENIED: 工具调用被策略拒绝。\n"
                            f"- tool: {tool_name}\n"
                            f"- reason: {reason}\n"
                            + (f"- approval_request_id: {approval_id}\n" if approval_id else "")
                            + "\n可选重试策略（择一）：\n"
                            "1) 改用更安全的只读工具（Read/Grep/Glob）先收集信息。\n"
                            "2) 缩小影响范围/调整参数（例如只读单文件、避免写入/执行）。\n"
                            "3) 使用 tool_search 搜索可用工具：{\"tool\":\"tool_search\",\"args\":{\"query\":\"read\"}}。\n"
                            "4) 若确实需要高风险操作，请走审批流程（如果返回 approval_request_id）。\n"
                        )
                        if (not auto_retry) or denied_count >= max_denied:
                            state.metadata["pause_requested"] = True
                        ok = False
                    else:
                        result_output = result.output if hasattr(result, 'output') else str(result)
                        ok = bool(getattr(result, "success", True))
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
                        f"首1K: {head}\n"
                        f"-- 内容过长({len(raw_output)}chars)，已截断 --\n"
                        f"尾1K: {tail}\n"
                        f"摘要生成中... 可用 sys_read_scratchpad({tool_use_id}) 获取完整智能摘要]"
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
        """
        import os as _os
        enabled = _os.getenv("AIPLAT_SELF_CORRECT_ENABLED", "true")
        if enabled in ("0", "false", "no") or not result:
            return ""

        correction_count = state.context.get("_correction_count", 0)
        if correction_count >= 1:
            return ""

        try:
            from core.harness.utils.prompt_loader import _sync_resolve

            # Step 1: Critique using reflection-critic template
            critique_prompt = _sync_resolve("reflection-critic",
                output=result[:2000],
                dimensions="正确性、完整性、逻辑一致性、格式规范性",
            )
            critique = await sys_llm_generate(
                None,
                [{"role": "user", "content": critique_prompt}],
                model_name=state.context.get("model", ""),
                max_tokens=4000,
            )
            critique_text = critique.content if hasattr(critique, 'content') else str(critique)
            if not critique_text or len(critique_text) < 20:
                return ""

            # Check if critic rejected the output
            import json as _json
            verdict = "PASS"
            try:
                parsed = _json.loads(critique_text) if critique_text.strip().startswith("{") else {}
                verdict = parsed.get("verdict", "PASS")
            except Exception:
                verdict = "PASS"  # Non-JSON response → don't correct

            if verdict == "PASS":
                return ""

            # Step 2: Improve using reflection-improve template
            improve_prompt = _sync_resolve("reflection-improve",
                previous_output=result[:1500],
                feedback=critique_text[:1000],
            )
            improved = await sys_llm_generate(
                None,
                [{"role": "user", "content": improve_prompt}],
                model_name=state.context.get("model", ""),
                max_tokens=4000,
            )
            improved_text = improved.content if hasattr(improved, 'content') else str(improved)
            if improved_text and len(improved_text) > 20:
                state.context["_correction_count"] = correction_count + 1
                state.context["_was_corrected"] = True
                logging.getLogger("loop.correct").info(
                    "Self-correction applied at step %d via reflection templates", state.step_count
                )
                return improved_text
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
        self._plan: List[Dict[str, Any]] = []
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
                prompt = (
                    "请为任务生成可执行的步骤计划。\n"
                    "要求：\n"
                    "1) 普通步骤用自然语言描述即可。\n"
                    "2) 若某一步需要调用工具，请用结构化 JSON 表达（单行）：\n"
                    "   {\"tool\":\"tool_name\",\"args\":{...}}\n"
                    "3) 若某一步需要调用 skill，也必须显式标注（单行）：\n"
                    "   {\"skill\":\"skill_name\",\"args\":{...}}\n"
                    f"\nTask: {state.context.get('task', '')}\n"
                )
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
            self._plan = [
                {"step": i + 1, "action": line.strip().lstrip("0123456789. ").strip()}
                for i, line in enumerate(response.content.split("\n"))
                if line.strip() and not line.strip().startswith("#")
            ]
        
        state.context["plan"] = self._plan
        self._current_node = "execute"
        state.current = LoopStateEnum.ACTING
        
        return state

    async def _execute(self, state: LoopState) -> LoopState:
        """Execution phase - execute plan steps with tool/skill support"""
        state.current = LoopStateEnum.ACTING
        
        current_step = state.context.get("current_step", 0)
        
        if current_step < len(self._plan):
            step = self._plan[current_step]
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
                            await self._trigger_hook(HookPhase.PRE_SKILL_USE, {"skill": skill_name, "skill_args": parsed_action.args, "format": parsed_action.format})
                            result = await sys_skill_call(
                                skill,
                                parsed_action.args,
                                context=skill_context,
                                user_id=skill_context.user_id,
                                session_id=skill_context.session_id,
                                trace_context={
                                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                                    "parent_span_id": state.context.get("_current_step_span_id"),
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
            
            if current_step + 1 >= len(self._plan):
                state.context["output"] = state.context.get("step_0_result", step_result)
                state.current = LoopStateEnum.FINISHED
                self._current_node = "finish"
        else:
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
