"""
Howl — Runtime Intervention Engine.

Inspired by ROSClaw's rosclaw-how: detects agent stalls/degradation and injects
minimal evidence-guided hints to redirect or unblock execution.

Four triggers, three strategies, zero LLM token cost on its own.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class StallReason(str, Enum):
    NONE = "none"
    SEMANTIC_STALL = "semantic_stall"         # same tool call 3+ times, no progress
    PARAMETER_LOOP = "parameter_loop"         # same params → same error repeatedly
    WALL_CLOCK_TIMEOUT = "wall_clock_timeout"  # no substantive output
    MODEL_UNAVAILABLE = "model_unavailable"    # model router reports failure


class InterventionStrategy(str, Enum):
    REDIRECT = "redirect"       # suggest alternative approach
    CLARIFY = "clarify"         # restate current state more clearly
    FALLBACK = "fallback"       # suggest switching model or tool


@dataclass
class InterventionResult:
    triggered: bool
    stall_reason: StallReason = StallReason.NONE
    strategy: InterventionStrategy = InterventionStrategy.REDIRECT
    hint_message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class Howl:
    """
    Runtime intervention engine.
    
    Checks for stalls after each loop step and injects hints when needed.
    
    Usage in loop.py:
      howl = Howl()
      result = howl.check(
          last_actions=state["recent_actions"],
          tool_errors=state["recent_errors"],
          last_output_time=loop.last_output_time,
          model_status=router.status(),
      )
      if result.triggered:
          messages.append({"role": "user", "content": result.hint_message})
    """

    # Semantic stall: same tool name 3+ consecutive times
    _SEMANTIC_STALL_THRESHOLD: int = 3
    # Parameter loop: same error 2+ consecutive times
    _PARAMETER_LOOP_THRESHOLD: int = 2
    # Wall clock: no substantive output (seconds)
    _WALL_CLOCK_LIMIT: float = 120.0

    _HINTS: Dict[StallReason, Dict[InterventionStrategy, str]] = {
        StallReason.SEMANTIC_STALL: {
            InterventionStrategy.REDIRECT: (
                "You have tried the same operation {count} times without progress. "
                "Consider breaking the task into smaller steps. Current state: {state_summary}"
            ),
            InterventionStrategy.CLARIFY: (
                "The last {count} attempts used the same tool without advancing the task. "
                "Key state keys available: {state_summary}. Use this context to try a different approach."
            ),
            InterventionStrategy.FALLBACK: (
                "Repeated attempts with the same operation have not succeeded. "
                "Consider delegating to a sub-agent or requesting user input."
            ),
        },
        StallReason.PARAMETER_LOOP: {
            InterventionStrategy.REDIRECT: (
                "The same parameters caused errors {count} times. "
                "Try adjusting: {param_diff}"
            ),
            InterventionStrategy.CLARIFY: (
                "Parameter errors detected: {param_diff}. "
                "Current context: {state_summary}"
            ),
            InterventionStrategy.FALLBACK: (
                "Parameter errors persist after {count} attempts. "
                "Consider using default values or asking for clarification."
            ),
        },
        StallReason.WALL_CLOCK_TIMEOUT: {
            InterventionStrategy.REDIRECT: (
                "You have been working on this task for {elapsed}s without producing output. "
                "Current state: {state_summary}. What is blocking progress?"
            ),
            InterventionStrategy.CLARIFY: (
                "No output in {elapsed:.0f}s. Available context: {state_summary}. "
                "If stuck, consider reporting what information you need."
            ),
            InterventionStrategy.FALLBACK: (
                "Task timed out after {elapsed:.0f}s. "
                "Consider restarting with a simpler approach or requesting assistance."
            ),
        },
        StallReason.MODEL_UNAVAILABLE: {
            InterventionStrategy.REDIRECT: "",
            InterventionStrategy.CLARIFY: "",
            InterventionStrategy.FALLBACK: (
                "Primary model unavailable ({model_error}). "
                "Falling back to: {fallback_model}"
            ),
        },
    }

    def check(
        self,
        *,
        last_actions: List[Dict[str, Any]] = None,
        tool_errors: List[Dict[str, Any]] = None,
        last_output_time: float = 0.0,
        model_status: str = "ok",
        model_error: str = "",
        fallback_model: str = "",
    ) -> InterventionResult:
        """
        Check for stall conditions and generate an intervention hint.
        Returns InterventionResult with trigger and hint.
        """
        last_actions = last_actions or []
        tool_errors = tool_errors or []

        # 1. Semantic stall detection
        if len(last_actions) >= self._SEMANTIC_STALL_THRESHOLD:
            recent = last_actions[-self._SEMANTIC_STALL_THRESHOLD:]
            tools = [a.get("tool", "") for a in recent]
            if len(set(tools)) == 1 and len(tools) == self._SEMANTIC_STALL_THRESHOLD:
                return InterventionResult(
                    triggered=True,
                    stall_reason=StallReason.SEMANTIC_STALL,
                    strategy=InterventionStrategy.REDIRECT,
                    hint_message=self._HINTS[StallReason.SEMANTIC_STALL][InterventionStrategy.REDIRECT].format(
                        count=self._SEMANTIC_STALL_THRESHOLD,
                        state_summary=self._summarize_state(last_actions),
                    ),
                    details={"tool": tools[0], "count": self._SEMANTIC_STALL_THRESHOLD},
                )

        # 2. Parameter loop
        if len(tool_errors) >= self._PARAMETER_LOOP_THRESHOLD:
            recent_err = tool_errors[-self._PARAMETER_LOOP_THRESHOLD:]
            err_msgs = [e.get("error", "") for e in recent_err]
            if len(set(err_msgs)) == 1 and len(err_msgs) == self._PARAMETER_LOOP_THRESHOLD:
                return InterventionResult(
                    triggered=True,
                    stall_reason=StallReason.PARAMETER_LOOP,
                    strategy=InterventionStrategy.REDIRECT,
                    hint_message=self._HINTS[StallReason.PARAMETER_LOOP][InterventionStrategy.REDIRECT].format(
                        count=self._PARAMETER_LOOP_THRESHOLD,
                        param_diff=err_msgs[0],
                        state_summary=self._summarize_state(last_actions),
                    ),
                    details={"error": err_msgs[0], "count": self._PARAMETER_LOOP_THRESHOLD},
                )

        # 3. Wall clock timeout
        if last_output_time > 0:
            elapsed = time.time() - last_output_time
            if elapsed > self._WALL_CLOCK_LIMIT:
                return InterventionResult(
                    triggered=True,
                    stall_reason=StallReason.WALL_CLOCK_TIMEOUT,
                    strategy=InterventionStrategy.CLARIFY,
                    hint_message=self._HINTS[StallReason.WALL_CLOCK_TIMEOUT][InterventionStrategy.CLARIFY].format(
                        elapsed=elapsed,
                        state_summary=self._summarize_state(last_actions),
                    ),
                    details={"elapsed_s": elapsed},
                )

        # 4. Model unavailable
        if model_status in ("unavailable", "unreachable", "error"):
            fallback = fallback_model
            if not fallback:
                try:
                    from core.harness.utils.model_injection import get_default_model
                    fallback = get_default_model("default")
                except Exception:
                    fallback = None  # Cannot resolve — skip fallback hint
            if fallback:
                hint = self._HINTS[StallReason.MODEL_UNAVAILABLE][InterventionStrategy.FALLBACK].format(
                    model_error=model_error,
                    fallback_model=fallback,
                )
                if hint:
                    return InterventionResult(
                        triggered=True,
                        stall_reason=StallReason.MODEL_UNAVAILABLE,
                        strategy=InterventionStrategy.FALLBACK,
                        hint_message=hint,
                        details={"model_status": model_status, "model_error": model_error},
                    )

        return InterventionResult(triggered=False)

    def _summarize_state(self, actions: List[Dict[str, Any]]) -> str:
        """Build a concise state summary from recent actions."""
        if not actions:
            return "no recent actions"
        tools_used = [a.get("tool", "?") for a in actions[-3:]]
        statuses = [a.get("status", "?") for a in actions[-3:]]
        return f"recent tools: {', '.join(tools_used)}; statuses: {', '.join(statuses)}"


__all__ = ["Howl", "InterventionResult", "StallReason", "InterventionStrategy"]
