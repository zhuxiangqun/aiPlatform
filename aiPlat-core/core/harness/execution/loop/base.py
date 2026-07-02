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
    """推断任务来源类型（Paper Data Recipes: coding/terminal/qa/system）"""
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
                pass
            return LoopResult(
                success=False,
                final_state=self._current_state,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )

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
