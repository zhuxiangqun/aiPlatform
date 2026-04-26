"""
Execution Loop - Base Implementation

Implements ILoop interface with ReAct (Reasoning + Acting) execution pattern.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import asyncio
import os
import time
import re
import uuid

from ..interfaces.loop import (
    ILoop,
    LoopState,
    LoopStateEnum,
    LoopConfig,
    LoopResult,
)
from ..infrastructure.hooks import HookManager, HookPhase, HookContext
from .tool_calling import parse_action_call, parse_tool_call
from ..syscalls import sys_llm_generate, sys_skill_call, sys_tool_call
from ..assembly import PromptAssembler
from ..kernel.runtime import get_kernel_runtime
from ..restatement.run_state import (
    default_run_state,
    format_run_state_for_prompt,
    normalize_run_state,
    restate_next_step,
    set_todo_status,
)


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

            # Post-loop hook
            await self._trigger_hook(HookPhase.POST_LOOP, {"state": self._current_state})
            await self._trigger_hook(HookPhase.STOP, {"state": self._current_state, "reason": stop_reason})
            await self._trigger_hook(HookPhase.SESSION_END, {"state": self._current_state, "reason": stop_reason})
            
            error = None
            if self._current_state.current == LoopStateEnum.PAUSED:
                error = self._current_state.context.get("error") or "paused"
            elif self._current_state.current == LoopStateEnum.ERROR:
                error = self._current_state.context.get("error") or "error"

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
            except Exception:
                pass
            return LoopResult(
                success=False,
                final_state=self._current_state,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )

    def should_continue(self, state: LoopState) -> bool:
        """Determine if loop should continue"""
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
            if os.getenv("AIPLAT_ENABLE_CONTEXT_COMPACTION", "false").lower() in ("1", "true", "yes", "y"):
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
        except Exception:
            pass
    
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
        state.history.append({
            "step": state.step_count,
            "node": self._current_node,
            "state": state.current.value
        })

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

        # Parse TODO_DONE markers from reasoning too (more "seamless")
        try:
            await self._apply_todo_done_markers(state, str(reasoning or ""), source="reasoning")
        except Exception:
            pass

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
                # Optional: auto-complete current todo when finishing (best-effort)
                try:
                    if os.getenv("AIPLAT_RUN_STATE_AUTO_COMPLETE_ON_DONE", "true").lower() in ("1", "true", "yes", "y"):
                        rs = state.context.get("run_state")
                        if isinstance(rs, dict):
                            # Use current_todo_id injected in prompt, if present
                            cur_id = None
                            try:
                                todo = rs.get("todo") if isinstance(rs.get("todo"), list) else []
                                from ..restatement.run_state import pick_next_todo

                                top = pick_next_todo(todo) if isinstance(todo, list) else None
                                cur_id = str((top or {}).get("id") or "").strip() or None
                            except Exception:
                                cur_id = None
                            if cur_id:
                                state.context["run_state"] = set_todo_status(rs, todo_id=cur_id, status="completed", source="auto_complete_on_done")
                                await self._persist_run_state(state, source="auto_complete_on_done", extra={"todo_id": cur_id})
                except Exception:
                    pass
                state.current = LoopStateEnum.FINISHED
                return state
        except Exception:
            pass

        state.current = LoopStateEnum.ACTING
        await self._trigger_hook(HookPhase.PRE_ACT, state.context)
        action_result = await self._act(state)
        state.context["action_result"] = action_result
        await self._trigger_hook(HookPhase.POST_ACT, state.context)

        # If a syscall requested pause (approval_required / policy_denied), stop here.
        if state.metadata.get("pause_requested"):
            state.current = LoopStateEnum.PAUSED
            return state

        state.current = LoopStateEnum.OBSERVING
        await self._trigger_hook(HookPhase.PRE_OBSERVE, state.context)
        observation = await self._observe(state)
        state.context["observation"] = observation
        await self._trigger_hook(HookPhase.POST_OBSERVE, state.context)

        # Optional: auto-complete todo items from explicit markers in logs/results.
        # Format: "TODO_DONE:<todo_id>" (can appear multiple times)
        try:
            await self._apply_todo_done_markers(state, f"{state.context.get('action_result','')}\n{observation}", source="observation")
        except Exception:
            pass

        if "DONE" in observation.upper() or "FINISHED" in observation.upper():
            state.current = LoopStateEnum.FINISHED

        return state

    async def _persist_run_state(self, state: LoopState, *, source: str, extra: Optional[Dict[str, Any]] = None) -> None:
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is None:
            return
        rs = state.context.get("run_state")
        if not isinstance(rs, dict):
            return
        try:
            from core.learning.manager import LearningManager
            from core.learning.types import LearningArtifactKind

            mgr = LearningManager(execution_store=store)
            run_id = state.context.get("_run_id") or state.context.get("run_id")
            await mgr.create_artifact(
                kind=LearningArtifactKind.RUN_STATE,
                target_type="run",
                target_id=str(run_id),
                version=f"run_state:{int(time.time())}",
                status="draft",
                payload=rs,
                metadata={"source": source, **(extra or {}), "locked": bool(rs.get("locked"))},
                trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                run_id=str(run_id),
            )
        except Exception:
            pass
        try:
            if hasattr(store, "append_run_event"):
                await store.append_run_event(
                    run_id=str(state.context.get("_run_id") or state.context.get("run_id")),
                    event_type="run_state",
                    trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                    tenant_id=state.context.get("tenant_id"),
                    payload={"source": source, **(extra or {})},
                )
        except Exception:
            pass

    async def _apply_todo_done_markers(self, state: LoopState, text: str, *, source: str) -> None:
        if os.getenv("AIPLAT_RUN_STATE_PARSE_TODO_DONE", "true").lower() not in ("1", "true", "yes", "y"):
            return
        done_ids = []
        for token in str(text or "").split():
            if token.startswith("TODO_DONE:"):
                done_ids.append(token.split("TODO_DONE:", 1)[1].strip())
        if not done_ids:
            return
        rs = state.context.get("run_state")
        if not isinstance(rs, dict):
            return
        for tid in done_ids[:20]:
            rs = set_todo_status(rs, todo_id=tid, status="completed", source=f"todo_done_marker:{source}")
        state.context["run_state"] = rs
        await self._persist_run_state(state, source=f"todo_done_marker:{source}", extra={"done_ids": done_ids[:20]})

    async def _reason(self, state: LoopState) -> str:
        """Reasoning phase"""
        if not self._model:
            return "No model available"

        # Optional: context compaction (best-effort)
        try:
            await self._maybe_compact_messages(state)
        except Exception:
            pass

        task = state.context.get("task", "")
        history = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in state.context.get("messages", [])[-5:]
        ])
        tools_desc, tools_desc_stats = self._build_tools_desc()
        # 上下文压力（best-effort）：用于渐进式披露预算
        try:
            max_tokens = float(getattr(self._config, "max_tokens", state.max_tokens) or state.max_tokens)
            used_tokens = float(getattr(state, "used_tokens", 0) or 0)
            pressure = (used_tokens / max_tokens) if max_tokens > 0 else 0.0
        except Exception:
            pressure = 0.0
        skills_desc, skills_desc_stats = self._build_skills_desc(context_pressure=pressure)
        # Best-effort: attach to state for observability/debugging
        try:
            state.metadata["tools_desc_stats"] = tools_desc_stats
            state.context["tools_desc_stats"] = tools_desc_stats
            state.metadata["skills_desc_stats"] = skills_desc_stats
            state.context["skills_desc_stats"] = skills_desc_stats
        except Exception:
            pass

        # P1-2: persist disclosure policy/budgets for replay (best-effort, de-duplicated)
        try:
            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            run_id0 = state.context.get("_run_id") or state.context.get("run_id")
            if store is not None and run_id0 and hasattr(store, "append_run_event"):
                # Emit only when policy/budget changes to reduce noise.
                key_fields = {
                    "disclosure_policy": skills_desc_stats.get("disclosure_policy"),
                    "per_skill_max_chars": skills_desc_stats.get("per_skill_max_chars"),
                    "total_max_chars": skills_desc_stats.get("total_max_chars"),
                    "skill_sop_recommended_max_chars": skills_desc_stats.get("skill_sop_recommended_max_chars"),
                }
                last = state.metadata.get("_skills_disclosure_last")
                if last != key_fields:
                    state.metadata["_skills_disclosure_last"] = dict(key_fields)
                    await store.append_run_event(
                        run_id=str(run_id0),
                        event_type="skills_disclosure",
                        trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                        tenant_id=state.context.get("tenant_id"),
                        payload={
                            "step_count": int(getattr(state, "step_count", 0) or 0),
                            "context_pressure": float(pressure),
                            "used_tokens": float(getattr(state, "used_tokens", 0) or 0),
                            "max_tokens": float(getattr(self._config, "max_tokens", state.max_tokens) or state.max_tokens),
                            "budgets": key_fields,
                        },
                    )
        except Exception:
            pass

        # P0: context shaping pipeline (observable, default enabled)
        try:
            await self._apply_context_shaping_pipeline(state)
        except Exception:
            pass

        # Restatement: load latest run_state and periodically refresh next_step
        try:
            await self._load_run_state_for_prompt(state)
            await self._maybe_restate_and_persist_run_state(state)
        except Exception:
            pass

        if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
            prompt = PromptAssembler().build_react_reasoning_messages(
                task=task,
                history=history,
                tools_desc=tools_desc,
                skills_desc=skills_desc,
                observation=state.context.get("observation", "None"),
            )
            rs = state.context.get("run_state")
            if isinstance(rs, dict):
                prompt.append({"role": "user", "content": format_run_state_for_prompt(rs)})
        else:
            prompt = f"""Task: {task}

History:
{history}

Available tools:
{tools_desc}

Available skills:
{skills_desc}

Observation: {state.context.get('observation', 'None')}

Think about what to do next. If using a tool/skill, respond with:
1) 优先（结构化）：
```json
{{"tool":"tool_name","args":{{...}}}}
```

Skill（必须显式标注，避免误触发）：
```json
{{"skill":"skill_name","args":{{...}}}}
```

2) 兼容旧格式（tool）：
ACTION: tool_name: argument

兼容旧格式（skill）：
SKILL: skill_name: argument

If finished, respond with:
DONE: final_answer
"""
            rs = state.context.get("run_state")
            if isinstance(rs, dict):
                prompt += "\n\n" + format_run_state_for_prompt(rs)
        try:
            trace_ctx = {
                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                "run_id": state.context.get("_run_id") or state.context.get("run_id"),
            }
            response = await sys_llm_generate(self._model, prompt, trace_context=trace_ctx)
            # Track token usage (best-effort) for compaction budgets.
            try:
                usage = getattr(response, "usage", None)
                if isinstance(usage, dict):
                    total = usage.get("total_tokens")
                    if total is None:
                        total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
                    state.used_tokens = float(getattr(state, "used_tokens", 0) or 0) + float(total or 0)
            except Exception:
                pass
            return response.content
        except Exception as e:
            return f"Model error: {e}"

    async def _load_run_state_for_prompt(self, state: LoopState) -> None:
        """
        Load latest run_state artifact (if any) into state.context["run_state"].
        """
        run_id = state.context.get("_run_id") or state.context.get("run_id")
        if not run_id:
            return
        if isinstance(state.context.get("run_state"), dict):
            return
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is None or not hasattr(store, "list_learning_artifacts"):
            state.context["run_state"] = default_run_state(run_id=str(run_id), task=str(state.context.get("task") or ""))
            return
        try:
            res = await store.list_learning_artifacts(target_type="run", target_id=str(run_id), kind="run_state", limit=10, offset=0)
            items = res.get("items") if isinstance(res, dict) else None
            if isinstance(items, list) and items:
                items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                payload = (items2[0] or {}).get("payload") if isinstance(items2[0], dict) else {}
                rs = normalize_run_state(payload, run_id=str(run_id))
                if not str(rs.get("task") or "").strip():
                    rs["task"] = str(state.context.get("task") or "")
                state.context["run_state"] = rs
                state.context["_run_state_artifact_id"] = (items2[0] or {}).get("artifact_id")
                return
        except Exception:
            pass
        state.context["run_state"] = default_run_state(run_id=str(run_id), task=str(state.context.get("task") or ""))

    async def _maybe_restate_and_persist_run_state(self, state: LoopState) -> None:
        """
        Periodically refresh run_state.next_step and persist (debounced).
        - restate: append run_event every N steps
        - persist: write learning artifact every M steps
        """
        run_id = state.context.get("_run_id") or state.context.get("run_id")
        if not run_id:
            return
        rs = state.context.get("run_state")
        if not isinstance(rs, dict):
            return
        if os.getenv("AIPLAT_ENABLE_RUN_STATE", "true").lower() not in ("1", "true", "yes", "y"):
            return

        try:
            restate_n = int(os.getenv("AIPLAT_RUN_STATE_RESTATE_EVERY_N_STEPS", "5"))
        except Exception:
            restate_n = 5
        try:
            persist_n = int(os.getenv("AIPLAT_RUN_STATE_PERSIST_EVERY_N_STEPS", "20"))
        except Exception:
            persist_n = 20

        step_count = int(getattr(state, "step_count", 0) or 0)
        if step_count <= 0:
            return

        # Always keep task filled
        if not str(rs.get("task") or "").strip():
            rs["task"] = str(state.context.get("task") or "")

        # Restate (cheap)
        if restate_n > 0 and (step_count % restate_n == 0):
            rs2 = restate_next_step(rs, step_count=step_count, last_error=state.context.get("error"))
            state.context["run_state"] = rs2
            # run event
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is not None and hasattr(store, "append_run_event"):
                    await store.append_run_event(
                        run_id=str(run_id),
                        event_type="run_state",
                        trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                        tenant_id=state.context.get("tenant_id"),
                        payload={"source": "loop", "step_count": step_count, "locked": bool(rs2.get("locked")), "next_step": rs2.get("next_step")},
                    )
            except Exception:
                pass

        # Persist (debounced)
        if persist_n > 0 and (step_count % persist_n == 0):
            try:
                if bool(state.context.get("run_state", {}).get("locked")):
                    return
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is None:
                    return
                from core.learning.manager import LearningManager
                from core.learning.types import LearningArtifactKind

                mgr = LearningManager(execution_store=store)
                await mgr.create_artifact(
                    kind=LearningArtifactKind.RUN_STATE,
                    target_type="run",
                    target_id=str(run_id),
                    version=f"run_state:{int(time.time())}",
                    status="draft",
                    payload=state.context.get("run_state"),
                    metadata={"source": "loop", "step_count": step_count, "locked": bool(state.context.get("run_state", {}).get("locked"))},
                    trace_id=state.context.get("_trace_id") or state.context.get("trace_id"),
                    run_id=str(run_id),
                )
            except Exception:
                pass

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

    async def _apply_context_shaping_pipeline(self, state: LoopState) -> None:
        """
        Multi-stage context shaping pipeline (skeleton + observability).

        Stages (in order, cost ascending):
        - budget_trim (already applied via tools/skills desc budgets)
        - prune (placeholder)
        - micro_compress (reuse existing compaction)
        - fold (placeholder)
        - auto_compress (placeholder)
        """
        if os.getenv("AIPLAT_ENABLE_CONTEXT_SHAPING_PIPELINE", "true").lower() not in ("1", "true", "yes", "y"):
            return

        stages = ["budget_trim", "prune", "micro_compress", "fold", "auto_compress"]
        pipeline_stats: Dict[str, Any] = {"enabled": True, "stages": [], "started_at": time.time()}

        async def _stage(name: str, fn) -> None:
            s_before = self._estimate_context_stats(state)
            err = None
            started = time.time()
            try:
                await fn()
            except Exception as e:
                err = str(e)
            ended = time.time()
            s_after = self._estimate_context_stats(state)
            item = {
                "stage": name,
                "started_at": started,
                "ended_at": ended,
                "duration_ms": (ended - started) * 1000.0,
                "before": s_before,
                "after": s_after,
                "error": err,
            }
            pipeline_stats["stages"].append(item)
            await self._append_run_event(state, event_type="context_shaping", payload=item)

        async def _budget_trim():
            return

        async def _prune():
            return

        async def _micro_compress():
            await self._maybe_compact_messages(state)

        async def _fold():
            return

        async def _auto_compress():
            return

        mapping = {
            "budget_trim": _budget_trim,
            "prune": _prune,
            "micro_compress": _micro_compress,
            "fold": _fold,
            "auto_compress": _auto_compress,
        }
        pipeline_stats["before"] = self._estimate_context_stats(state)
        for stg in stages:
            await _stage(stg, mapping[stg])
        pipeline_stats["after"] = self._estimate_context_stats(state)
        pipeline_stats["ended_at"] = time.time()
        pipeline_stats["total_duration_ms"] = (pipeline_stats["ended_at"] - pipeline_stats["started_at"]) * 1000.0
        try:
            state.metadata["context_shaping_stats"] = pipeline_stats
            state.context["context_shaping_stats"] = pipeline_stats
        except Exception:
            pass

    async def _maybe_compact_messages(self, state: LoopState) -> None:
        """
        When token budget pressure is high, compact older messages into a summary.

        Inspired by OpenClaw:
        - Preserve identifiers (UUIDs, hashes, filenames)
        - Keep recent turns verbatim
        - Best-effort; fail-open to no compaction
        """
        import os
        import re

        if os.getenv("AIPLAT_ENABLE_CONTEXT_COMPACTION", "false").lower() not in ("1", "true", "yes", "y"):
            return

        msgs = state.context.get("messages")
        if not isinstance(msgs, list) or len(msgs) < 8:
            return

        max_tokens = float(getattr(self._config, "max_tokens", None) or getattr(state, "max_tokens", 0) or 0)
        used_tokens = float(getattr(state, "used_tokens", 0) or 0)
        if max_tokens <= 0:
            return

        threshold = float(os.getenv("AIPLAT_CONTEXT_COMPACTION_THRESHOLD", "0.8") or "0.8")
        if (used_tokens / max_tokens) < threshold:
            return

        protect_last_n = int(os.getenv("AIPLAT_CONTEXT_COMPACTION_PROTECT_LAST_N", "6") or "6")
        protect_last_n = max(2, min(protect_last_n, 50))
        head = msgs[:-protect_last_n]
        tail = msgs[-protect_last_n:]

        # Extract identifiers to preserve
        text = "\n".join([str(m.get("content", "")) for m in head if isinstance(m, dict)])
        uuid_re = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
        sha_re = r"\b[0-9a-f]{12,64}\b"
        file_re = r"\b[\w./-]+\.(?:py|ts|tsx|js|json|md|yaml|yml|toml|sql)\b"
        ids = set(re.findall(uuid_re, text, flags=re.IGNORECASE))
        ids |= set(re.findall(file_re, text, flags=re.IGNORECASE))
        # Limit hashes (avoid huge noise)
        for h in re.findall(sha_re, text, flags=re.IGNORECASE):
            if 12 <= len(h) <= 40:
                ids.add(h)
        ids_list = sorted(list(ids))[:50]

        summary_prompt = (
            "你是一个对话压缩器。请将以下历史对话压缩为一段“可继续执行任务”的摘要。\n"
            "强制要求：\n"
            "1) 保留关键结论、进行中的计划、未解决的问题。\n"
            "2) 严格保留并逐字输出任何标识符（UUID/哈希/文件名/路径/ID）。\n"
            "3) 不要编造不存在的事实。\n\n"
            f"需要保留的标识符（如出现过）：{', '.join(ids_list) if ids_list else '(none)'}\n\n"
            "历史对话（将被压缩）：\n"
            + "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in head if isinstance(m, dict)])
            + "\n\n输出格式：直接输出摘要文本（不要加额外标题）。"
        )

        trace_ctx = {
            "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
            "run_id": state.context.get("_run_id") or state.context.get("run_id"),
        }
        resp = await sys_llm_generate(self._model, summary_prompt, trace_context=trace_ctx)
        summary_text = str(getattr(resp, "content", "") or "").strip()
        if not summary_text:
            return

        state.context["messages"] = [
            {
                "role": "system",
                "content": "CONTEXT_SUMMARY:\n" + summary_text + ("\n\nPRESERVED_IDENTIFIERS:\n" + "\n".join(ids_list) if ids_list else ""),
            }
        ] + tail
        state.metadata["control_action"] = "compact_context_summary"
        state.metadata["compacted_messages"] = True
        state.metadata["compaction_stats"] = {"before": len(msgs), "after": len(state.context["messages"]), "preserved_ids": len(ids_list)}

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

        try:
            from core.apps.skills import get_skill_registry

            reg = get_skill_registry()
            names = reg.list_skills()
        except Exception:
            names = []

        stats["skills_total"] = len(names)
        if not names:
            return "No skills available (use skill_find to discover)", stats

        lines: List[str] = []
        for name in sorted([str(x) for x in names]):
            # best-effort: hide denied skills (OpenCode behavior)
            try:
                from core.apps.tools.skill_tools import resolve_skill_permission

                if resolve_skill_permission(name) == "deny":
                    continue
            except Exception:
                pass
            try:
                s = reg.get(name)  # type: ignore[name-defined]
                cfg = s.get_config() if s else None
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

    async def _act(self, state: LoopState) -> str:
        """Acting phase - execute tool or skill."""
        reasoning = state.context.get("reasoning", "")
        parsed = parse_action_call(reasoning)
        # --- routing candidates snapshot (router-time) ---
        routing_decision_id = f"rtd_{uuid.uuid4().hex[:16]}"
        state.context["_routing_decision_id"] = routing_decision_id

        def _coding_policy_profile_for_skill(skill_obj: Any) -> str:
            """
            Determine effective coding policy profile for a selected skill.
            Default off; can be enabled via env:
            - AIPLAT_CODING_POLICY_PROFILE_WORKSPACE
            - AIPLAT_CODING_POLICY_PROFILE_ENGINE
            """
            try:
                config = getattr(skill_obj, "_config", None) or getattr(skill_obj, "get_config", lambda: None)()
                meta = getattr(config, "metadata", None) if config is not None else None
                meta = meta if isinstance(meta, dict) else {}
                category = str(meta.get("category") or getattr(config, "category", "") or "").lower()
                tags = meta.get("tags") or []
                tags = [str(t).lower() for t in tags] if isinstance(tags, list) else []
                is_coding = (category == "coding") or ("coding" in tags) or ("code" in tags)
                if not is_coding:
                    return "off"
                scope = str(state.context.get("skill_scope") or "engine").lower()
                if scope == "workspace":
                    return os.getenv("AIPLAT_CODING_POLICY_PROFILE_WORKSPACE", "off").strip().lower()
                return os.getenv("AIPLAT_CODING_POLICY_PROFILE_ENGINE", "off").strip().lower()
            except Exception:
                return "off"

        async def _emit_routing_decision(*, selected_kind: str, selected_name: str = "", query_excerpt: str = "") -> None:
            """Emit decision-level routing event as funnel denominator."""
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is None:
                    return
                qx = str(query_excerpt or "").strip()
                if not qx:
                    # best-effort: last user message then task
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
                await store.add_syscall_event(
                    {
                        "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                        "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                        "tenant_id": state.context.get("tenant_id"),
                        "kind": "routing",
                        "name": "routing_decision",
                        "status": "decision",
                        "start_time": end_ts,
                        "end_time": end_ts,
                        "duration_ms": 0.0,
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
                    }
                )
            except Exception:
                return

        async def _emit_skill_candidates_snapshot(*, selected_kind: str, selected_name: str = "") -> None:
            """
            Emit candidates even when no skill is invoked (tool chosen / no action).
            Stored as syscall_events(kind=routing, name=skill_candidates_snapshot) so it joins funnel aggregation.
            """
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is None:
                    return

                # best-effort query text from current task + last user message
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
                    return

                def _norm(s: str) -> str:
                    s0 = str(s or "").lower().strip()
                    s0 = re.sub(r"[\s\-\._/]+", " ", s0)
                    s0 = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s0)
                    return s0.strip()

                def _tokenize(s: str) -> set[str]:
                    s0 = _norm(s)
                    if not s0:
                        return set()
                    toks = set()
                    for w in s0.split():
                        if len(w) >= 2:
                            toks.add(w)
                    for seg in re.findall(r"[\u4e00-\u9fff]{2,}", s0):
                        for i in range(0, max(0, len(seg) - 1)):
                            toks.add(seg[i : i + 2])
                    return toks

                qt = _tokenize(q)
                if not qt:
                    return

                candidates: List[Dict[str, Any]] = []

                async def _scan_mgr(mgr: Any, scope0: str) -> None:
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
                            blob = " ".join(
                                [
                                    nm,
                                    desc,
                                    " ".join([str(x) for x in (tc or [])]),
                                    " ".join([str(x) for x in (kw.get("objects") or [])]),
                                    " ".join([str(x) for x in (kw.get("actions") or [])]),
                                    " ".join([str(x) for x in (kw.get("constraints") or [])]),
                                ]
                            )
                            st = _tokenize(blob)
                            if not st:
                                continue
                            inter = qt & st
                            if not inter:
                                continue
                            score = float(len(inter))
                            for t in (tc or [])[:10]:
                                tt = str(t or "").strip()
                                if tt and tt in q:
                                    score += 3.0
                                    break
                            # permission hints (best-effort)
                            perm = None
                            exec_perm = None
                            try:
                                from core.apps.tools.skill_tools import resolve_skill_permission, resolve_executable_skill_permission

                                perm = resolve_skill_permission(nm)
                                if skill_kind == "executable":
                                    exec_perm = resolve_executable_skill_permission(nm)
                            except Exception:
                                perm = None
                                exec_perm = None
                            candidates.append(
                                {
                                    "skill_id": sid,
                                    "name": nm,
                                    "scope": scope0,
                                    "skill_kind": skill_kind,
                                    "score": score,
                                    "overlap": sorted(list(inter))[:12],
                                    "perm": perm,
                                    "exec_perm": exec_perm,
                                }
                            )
                        except Exception:
                            continue

                await _scan_mgr(getattr(runtime, "workspace_skill_manager", None), "workspace")
                await _scan_mgr(getattr(runtime, "skill_manager", None), "engine")
                candidates.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
                top = candidates[:8]
                end_ts = time.time()
                await store.add_syscall_event(
                    {
                        "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                        "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                        "tenant_id": state.context.get("tenant_id"),
                        "kind": "routing",
                        "name": "skill_candidates_snapshot",
                        "status": "snapshot",
                        "start_time": end_ts,
                        "end_time": end_ts,
                        "duration_ms": 0.0,
                        "args": {
                            "routing_decision_id": routing_decision_id,
                            "step_count": int(getattr(state, "step_count", 0) or 0),
                            "selected_kind": selected_kind,
                            "selected_name": selected_name,
                            "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),
                            "query_excerpt": q[:220],
                            "candidates": top,
                        },
                        "created_at": end_ts,
                    }
                )
                # return top candidates for explain computation
                return top
            except Exception:
                return []

        async def _emit_routing_explain(*, selected_kind: str, selected_name: str, candidates_top: List[Dict[str, Any]], result_status: str = "", result_error: str = "") -> None:
            """
            Emit decision explain event. This is a higher-level, merged view that makes
            "why tool/no_action/why not top1" debuggable without joining many streams.
            """
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is None:
                    return
                # best-effort query excerpt
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

                # compute ranks/scores
                sel_id = str(selected_name or "")
                top1 = candidates_top[0] if candidates_top and isinstance(candidates_top[0], dict) else {}
                top1_id = str(top1.get("skill_id") or top1.get("name") or "")
                top1_score = float(top1.get("score") or 0.0) if top1 else None
                sel_rank = None
                sel_score = None
                for idx, c in enumerate(candidates_top or []):
                    if not isinstance(c, dict):
                        continue
                    cid = str(c.get("skill_id") or c.get("name") or "")
                    if cid == sel_id:
                        sel_rank = idx
                        sel_score = float(c.get("score") or 0.0)
                        break
                gap = None
                try:
                    if top1_score is not None and sel_score is not None:
                        gap = float(top1_score - sel_score)
                except Exception:
                    gap = None

                # top1 gate hints (permission-based; best-effort)
                top1_gate = None
                try:
                    if str(top1.get("perm") or "") == "deny":
                        top1_gate = "permission_deny"
                    elif str(top1.get("skill_kind") or "") == "executable" and str(top1.get("exec_perm") or "") == "ask":
                        top1_gate = "approval_required"
                except Exception:
                    top1_gate = None

                end_ts = time.time()
                await store.add_syscall_event(
                    {
                        "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                        "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                        "tenant_id": state.context.get("tenant_id"),
                        "kind": "routing",
                        "name": "routing_explain",
                        "status": "explain",
                        "start_time": end_ts,
                        "end_time": end_ts,
                        "duration_ms": 0.0,
                        "args": {
                            "routing_decision_id": routing_decision_id,
                            "step_count": int(getattr(state, "step_count", 0) or 0),
                            "selected_kind": str(selected_kind),
                            "selected_name": sel_id,
                            "selected_skill_id": sel_id if str(selected_kind) == "skill" else "",
                            "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),
                            "query_excerpt": qx[:220],
                            "candidates_top": (candidates_top or [])[:5],
                            "top1_skill_id": top1_id,
                            "top1_score": top1_score,
                            "top1_gate_hint": top1_gate,
                            "selected_rank": sel_rank,
                            "selected_score": sel_score,
                            "score_gap": gap,
                            "result_status": str(result_status or ""),
                            "result_error": str(result_error or ""),
                        },
                        "created_at": end_ts,
                    }
                )
            except Exception:
                return

        async def _emit_routing_strict_eval(*, selected_kind: str, selected_name: str, candidates_top: List[Dict[str, Any]]) -> None:
            """
            Strict miss-rate evaluation (Iteration 4.1).
            Definition (MVP, env configurable):
            - Determine eligible_top1: first candidate that is not gated by permission:
              - perm != deny
              - if skill_kind==executable: exec_perm != ask
            - strict_eligible = eligible_top1 exists AND eligible_top1.score >= threshold
            - outcome:
              - if strict_eligible:
                - selected_kind != skill => miss_tool / miss_no_action
                - selected_kind == skill and selected != eligible_top1 => misroute
                - selected_kind == skill and selected == eligible_top1 => hit
              - else: no_eligible
            """
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is None:
                    return
                thr = float(os.getenv("AIPLAT_ROUTING_STRICT_MIN_SCORE", "3.0") or "3.0")
                # compute eligible top1
                eligible = None
                gated_top1_reason = None
                top1 = candidates_top[0] if candidates_top and isinstance(candidates_top[0], dict) else None
                if top1 is not None:
                    try:
                        if str(top1.get("perm") or "") == "deny":
                            gated_top1_reason = "permission_deny"
                        elif str(top1.get("skill_kind") or "") == "executable" and str(top1.get("exec_perm") or "") == "ask":
                            gated_top1_reason = "approval_required"
                    except Exception:
                        gated_top1_reason = None
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
                try:
                    eligible_score = float((eligible or {}).get("score") or 0.0) if eligible else None
                except Exception:
                    eligible_score = None
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
                await store.add_syscall_event(
                    {
                        "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                        "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                        "tenant_id": state.context.get("tenant_id"),
                        "kind": "routing",
                        "name": "routing_strict_eval",
                        "status": "eval",
                        "start_time": end_ts,
                        "end_time": end_ts,
                        "duration_ms": 0.0,
                        "args": {
                            "routing_decision_id": routing_decision_id,
                            "step_count": int(getattr(state, "step_count", 0) or 0),
                            "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),
                            "threshold": thr,
                            "selected_kind": sel_kind,
                            "selected_name": sel_name,
                            "selected_skill_id": sel_name if sel_kind == "skill" else "",
                            "eligible_top1_skill_id": eligible_id,
                            "eligible_top1_score": eligible_score,
                            "eligible_top1_exists": bool(eligible_id),
                            "strict_eligible": strict_eligible,
                            "strict_outcome": outcome,
                            "gated_top1_reason": gated_top1_reason,
                        },
                        "created_at": end_ts,
                    }
                )
            except Exception:
                return

        if not parsed:
            await _emit_routing_decision(selected_kind="none")
            top = await _emit_skill_candidates_snapshot(selected_kind="none")
            await _emit_routing_strict_eval(selected_kind="none", selected_name="", candidates_top=top)
            await _emit_routing_explain(selected_kind="none", selected_name="", candidates_top=top, result_status="no_action", result_error="")
            return "No action to execute"

        if parsed.kind == "skill":
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
                    prof = _coding_policy_profile_for_skill(skill)
                    state.context["_coding_policy_profile"] = prof
                    await _emit_routing_decision(selected_kind="skill", selected_name=str(skill_name))
                    top = await _emit_skill_candidates_snapshot(selected_kind="skill", selected_name=str(skill_name))
                    await _emit_routing_strict_eval(selected_kind="skill", selected_name=str(skill_name), candidates_top=top)
                    from ..interfaces import SkillContext
                    await self._trigger_hook(HookPhase.PRE_SKILL_USE, {"skill": skill_name, "skill_args": skill_args, "format": parsed.format})
                    try:
                        skill_context = SkillContext(
                            session_id=state.context.get("session_id", "default"),
                            user_id=state.context.get("user_id", "system"),
                            variables=skill_args,
                        )
                        result = await sys_skill_call(
                            skill,
                            skill_args,
                            context=skill_context,
                            user_id=skill_context.user_id,
                            session_id=skill_context.session_id,
                            trace_context={
                                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                                "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                                "tenant_id": state.context.get("tenant_id"),
                                "routing_decision_id": routing_decision_id,
                                "coding_policy_profile": prof,
                                "routing_candidates_emitted": True,
                            },
                        )
                        # Standardized approval/policy states for skills (P1)
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
                    # explain with execution outcome (best-effort)
                    try:
                        st = "success" if getattr(result, "success", False) else "failed"
                        await _emit_routing_explain(
                            selected_kind="skill",
                            selected_name=str(skill_name),
                            candidates_top=top,
                            result_status=st,
                            result_error=str(getattr(result, "error", "") or ""),
                        )
                    except Exception:
                        pass
                    await self._trigger_hook(HookPhase.POST_SKILL_USE, {"skill": skill_name, "result": result_output, "format": parsed.format})
                    return str(result_output)
            return f"Skill not found: {skill_name}"

        tool_name = parsed.name
        tool_args = parsed.args
        state.context["tool_call"] = {"tool": tool_name, "args": tool_args, "format": parsed.format}
        state.context["_coding_policy_profile"] = "off"
        await _emit_routing_decision(selected_kind="tool", selected_name=str(tool_name))
        top = await _emit_skill_candidates_snapshot(selected_kind="tool", selected_name=str(tool_name))
        await _emit_routing_strict_eval(selected_kind="tool", selected_name=str(tool_name), candidates_top=top)
        await _emit_routing_explain(selected_kind="tool", selected_name=str(tool_name), candidates_top=top, result_status="tool_selected", result_error="")

        for tool in self._tools:
            if str(getattr(tool, 'name', '')).strip().lower() == str(tool_name).strip().lower():
                # Approval hooks (may block)
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
                    # If we are resuming an approval-required tool call, attach the approval_request_id
                    # so PolicyGate can validate and allow execution.
                    approval_meta = state.context.get("approval") if isinstance(state.context.get("approval"), dict) else {}
                    approval_req_id = approval_meta.get("approval_request_id")
                    if approval_req_id:
                        try:
                            tool_args = dict(tool_args or {})
                            tool_args["_approval_request_id"] = approval_req_id
                        except Exception:
                            pass
                    result = await sys_tool_call(
                        tool,
                        tool_args,
                        user_id=state.context.get("user_id", "system"),
                        session_id=state.context.get("session_id", "default"),
                        trace_context={
                            "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                            "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                            "tenant_id": state.context.get("tenant_id"),
                            "routing_decision_id": routing_decision_id,
                            "coding_policy_profile": str(state.context.get("_coding_policy_profile") or "off"),
                        },
                    )
                    # Standardized syscall result handling
                    if getattr(result, "error", None) == "approval_required":
                        state.context["error"] = "approval_required"
                        state.context["approval"] = getattr(result, "metadata", {}) or {}
                        state.metadata["pause_requested"] = True
                        result_output = "Approval required"
                        ok = False
                    elif getattr(result, "error", None) == "policy_denied":
                        state.context["error"] = "policy_denied"
                        state.context["policy"] = getattr(result, "metadata", {}) or {}
                        # Claude Code-like: provide retry guidance and optionally allow the loop to continue
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
                # explain with execution outcome (best-effort)
                try:
                    if getattr(result, "error", None) == "approval_required":
                        st = "approval_required"
                    elif getattr(result, "error", None) == "policy_denied":
                        st = "policy_denied"
                    else:
                        st = "success" if ok else "failed"
                    await _emit_routing_explain(
                        selected_kind="tool",
                        selected_name=str(tool_name),
                        candidates_top=top,
                        result_status=st,
                        result_error=str(getattr(result, "error", "") or ""),
                    )
                except Exception:
                    pass
                # Record tool stats for observability-driven control
                state.metadata["tool_calls"] = int(state.metadata.get("tool_calls", 0) or 0) + 1
                if not ok:
                    state.metadata["tool_failures"] = int(state.metadata.get("tool_failures", 0) or 0) + 1
                await self._trigger_hook(HookPhase.POST_TOOL_USE, {"tool_name": tool_name, "result": result_output, "format": parsed.format})
                await self._trigger_hook(HookPhase.POST_APPROVAL_CHECK, {"tool_name": tool_name, "allowed": True})
                return str(result_output)

        return f"Tool not found: {tool_name}"

    async def _observe(self, state: LoopState) -> str:
        """Observing phase"""
        return state.context.get("action_result", "")


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
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
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
                },
            )
            try:
                usage = getattr(response, "usage", None)
                if isinstance(usage, dict):
                    total = usage.get("total_tokens")
                    if total is None:
                        total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
                    state.used_tokens = float(getattr(state, "used_tokens", 0) or 0) + float(total or 0)
            except Exception:
                pass
            
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
                    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
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
