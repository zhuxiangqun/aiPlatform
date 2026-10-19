"""
Compiled ReAct graph (Reason -> Act -> Observe) using internal CompiledGraph engine.

Purpose:
- Allow checkpoint/restore/resume to close the loop on a path that does not depend on external langgraph.
- Trigger CallbackManager events, feeding the server lifespan persistence handler to write into ExecutionStore.

Phase 9: node functions inline the syscall channel, no longer depending on the parallel ReAct implementation in nodes/.
"""

from __future__ import annotations
import logging

import os
from typing import Any, Dict, List, Optional

from ..core import GraphBuilder, GraphConfig, NodeResult, CompiledGraph
from ...tool_calling import parse_action_call, parse_tool_call
from ....syscalls import sys_llm_generate, sys_tool_call
from ....assembly import MessageFormatter


def _build_reason_prompt(state: Dict[str, Any]) -> str:
    messages = state.get("messages") or []
    history = "\n".join([
        f"{msg.get('role', 'user')}: {msg.get('content', '')}"
        for msg in messages[-5:]
    ])
    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true").lower() in ("1", "true", "yes", "y"):
        return MessageFormatter().build_langgraph_reason_messages(
            history=history,
            reasoning=str(state.get("reasoning", "") or ""),
            action=str(state.get("action", "") or ""),
            observation=str(state.get("observation", "") or ""),
        )
    return f"""Current state:
- History: {history}
- Reasoning: {state.get('reasoning','')}
- Action: {state.get('action','')}
- Observation: {state.get('observation','')}

What should I do next?

Prefer structured tool calls (recommended):
```json
{{"tool":"tool_name","args":{{...}}}}
```

Legacy format:
ACTION: tool_name: {{json_or_text}}

If finished, respond with: DONE
"""


def _find_tool(tools: List[Any], name: str) -> Optional[Any]:
    for tool in tools:
        if hasattr(tool, 'name') and tool.name == name:
            return tool
    return None


def create_compiled_react_graph(
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    max_steps: int = 10,
    graph_name: str = "compiled_react",
) -> CompiledGraph:
    _tools = tools or []
    builder = GraphBuilder(name=graph_name)

    async def reason(state: Dict[str, Any]) -> NodeResult:
        prompt = _build_reason_prompt(state)
        if model:
            # Optional per-run temperature override (e.g. evaluator judges set 0.0
            # for deterministic verdicts). Absent → model default, unchanged behavior.
            _temp = None
            _ctx = state.get("context")
            if isinstance(_ctx, dict):
                _temp = _ctx.get("_llm_temperature")
            response = await sys_llm_generate(
                model, prompt, temperature=_temp,
                trace_context={"source": "compiled_react"},
            )
            reasoning = response.content
        else:
            reasoning = "No model available"
        state["reasoning"] = reasoning
        ctx = state.get("context")
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx
        ctx["reasoning"] = reasoning
        try:
            from core.harness.execution.completion_receipt import remember_repair_candidates

            remember_repair_candidates(ctx)
        except Exception:
            logging.getLogger(__name__).debug("remember_repair_candidates skipped", exc_info=True)
        step_count = int(state.get("step_count", 0) or 0) + 1
        state["step_count"] = step_count
        from core.harness.execution.completion_receipt import is_terminal_done_marker

        if is_terminal_done_marker(reasoning):
            state["observation"] = "DONE"
            return NodeResult(success=True, output={"reasoning": reasoning}, next_node=None)
        return NodeResult(success=True, output={"reasoning": reasoning}, next_node="act")

    async def act(state: Dict[str, Any]) -> NodeResult:
        action_result = ""
        reasoning = state.get("reasoning", "") or ""
        parsed = parse_action_call(reasoning)
        action_name = None
        tool_args: Dict[str, Any] = {}

        if parsed:
            if parsed.kind == "skill":
                action_name = None
            else:
                action_name = parsed.name
                tool_args = parsed.args or {}
        else:
            action_name = _parse_action_from_text(reasoning)

        tool_failed = False
        if action_name and _tools:
            tool = _find_tool(_tools, action_name)
            if tool:
                try:
                    ctx = state.get("context")
                    if not isinstance(ctx, dict):
                        ctx = {}
                        state["context"] = ctx
                    from core.harness.execution.completion_receipt import (
                        block_extra_repair_verify,
                        block_skipped_repair_write,
                    )

                    _blocked_verify = block_extra_repair_verify(ctx, action_name, tool_args)
                    if _blocked_verify:
                        action_result = f"Denied: {_blocked_verify}"
                        state["action"] = action_name
                        state["observation"] = action_result
                        try:
                            from core.harness.execution.completion_receipt import (
                                record_tool_receipt,
                            )

                            record_tool_receipt(
                                ctx,
                                tool=str(action_name or ""),
                                status="failed",
                                detail=action_result[:500],
                            )
                        except Exception:
                            logging.getLogger(__name__).debug(
                                "deny receipt skipped", exc_info=True
                            )
                        return NodeResult(
                            success=False,
                            output={"observation": action_result},
                            next_node="observe",
                        )
                    _blocked_write = block_skipped_repair_write(ctx, action_name, tool_args)
                    if _blocked_write:
                        action_result = f"Denied: {_blocked_write}"
                        state["action"] = action_name
                        state["observation"] = action_result
                        try:
                            from core.harness.execution.completion_receipt import (
                                record_tool_receipt,
                            )

                            record_tool_receipt(
                                ctx,
                                tool=str(action_name or ""),
                                status="failed",
                                detail=action_result[:500],
                            )
                        except Exception:
                            logging.getLogger(__name__).debug(
                                "deny receipt skipped", exc_info=True
                            )
                        return NodeResult(
                            success=False,
                            output={"observation": action_result},
                            next_node="observe",
                        )
                    result = await sys_tool_call(
                        tool,
                        tool_args,
                        user_id=str(ctx.get("user_id", "system")),
                        session_id=str(ctx.get("session_id", "default")),
                        trace_context={
                            "trace_id": ctx.get("_trace_id") or ctx.get("trace_id"),
                            "run_id": ctx.get("_run_id") or ctx.get("run_id"),
                            "tenant_id": ctx.get("tenant_id"),
                        },
                    )
                    try:
                        from core.harness.execution.completion_receipt import (
                            maybe_note_repair_fs_delta,
                        )

                        maybe_note_repair_fs_delta(ctx)
                    except Exception:
                        logging.getLogger(__name__).debug(
                            "maybe_note_repair_fs_delta skipped", exc_info=True
                        )
                    tool_failed = getattr(result, "success", True) is False
                    if tool_failed:
                        err = str(getattr(result, "error", "") or result.output or "tool_failed")
                        action_result = (
                            err
                            if err.lstrip().lower().startswith(
                                ("error:", "denied:", "skill error:", "tool not found")
                            )
                            else f"Error: {err}"
                        )
                    else:
                        action_result = str(result.output or result.error or "Success")
                except Exception as e:
                    action_result = f"Error: {str(e)}"
                    tool_failed = True
            else:
                action_result = f"Tool not found: {action_name}"
                tool_failed = True
        elif action_name:
            action_result = f"Action: {action_name}"
        else:
            action_result = "No action to execute"

        state["action"] = action_name
        state["observation"] = action_result
        # Only real tool attempts become receipts. "No action" / bare Action: must not look like success.
        attempted = bool(action_name) and bool(_tools)
        node_ok = True
        if attempted:
            try:
                from core.harness.execution.completion_receipt import (
                    infer_receipt_status,
                    record_tool_receipt,
                )

                ctx = state.get("context")
                if not isinstance(ctx, dict):
                    ctx = {}
                    state["context"] = ctx
                seal = "failed" if tool_failed else infer_receipt_status(action_result)
                record_tool_receipt(
                    ctx,
                    tool=str(action_name or ""),
                    status=seal,
                    detail=str(action_result or "")[:500],
                )
                node_ok = seal == "ok"
            except Exception:
                logging.getLogger(__name__).debug("tool receipt skipped", exc_info=True)
                node_ok = not tool_failed
        return NodeResult(
            success=node_ok,
            output={"action": action_name, "observation": action_result},
            next_node="observe",
        )

    async def observe(state: Dict[str, Any]) -> NodeResult:
        observation = state.get("observation", "")
        if model and observation:
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true").lower() in ("1", "true", "yes", "y"):
                prompt = MessageFormatter().build_langgraph_observe_messages(
                    observation=str(observation)
                )
            else:
                prompt = f"Observation: {observation}\nWhat does this mean for the next step?"
            try:
                await sys_llm_generate(model, prompt, trace_context={"source": "compiled_react_observe"})
            except Exception as e:
                logging.warning(str(e), exc_info=True)

        obs = str(state.get("observation", "") or "")
        step_count = int(state.get("step_count", 0) or 0)
        max_steps_local = int(state.get("max_steps", max_steps) or max_steps)
        from core.harness.execution.completion_receipt import is_terminal_done_marker

        if is_terminal_done_marker(obs) or step_count >= max_steps_local:
            return NodeResult(success=True, output={}, next_node=None)
        return NodeResult(success=True, output={}, next_node="reason")

    (
        builder.add_node("reason", reason)
        .add_node("act", act)
        .add_node("observe", observe)
        .add_edge("reason", "act")
        .add_edge("act", "observe")
        .add_edge("observe", "reason")
        .set_entry_point("reason")
    )

    return builder.build()


def _parse_action_from_text(reasoning: str) -> Optional[str]:
    """Legacy ACTION: fallback — line-leading marker only (not INACTION:/…)."""
    parsed = parse_tool_call(reasoning)
    if parsed and parsed.format == "action":
        return parsed.tool_name
    return None
