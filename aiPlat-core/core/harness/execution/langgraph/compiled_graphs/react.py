"""
Compiled ReAct graph (Reason -> Act -> Observe) using internal CompiledGraph engine.

目的：
- 让 checkpoint/restore/resume 能在"不依赖外部 langgraph"路径上闭环。
- 触发 CallbackManager 事件，配合 server lifespan 的落库 handler 写入 ExecutionStore。

Phase 9: 节点函数内联 syscall 通道，不再依赖 nodes/ 的并行 ReAct 实现。
"""

from __future__ import annotations
import logging

import os
from typing import Any, Dict, List, Optional

from ..core import GraphBuilder, GraphConfig, NodeResult, CompiledGraph
from ...tool_calling import parse_action_call
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

优先使用结构化工具调用（推荐）：
```json
{{"tool":"tool_name","args":{{...}}}}
```

兼容旧格式：
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
            response = await sys_llm_generate(model, prompt, trace_context={"source": "compiled_react"})
            reasoning = response.content
        else:
            reasoning = "No model available"
        state["reasoning"] = reasoning
        step_count = int(state.get("step_count", 0) or 0) + 1
        state["step_count"] = step_count
        if "DONE" in reasoning.upper():
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

        if action_name and _tools:
            tool = _find_tool(_tools, action_name)
            if tool:
                try:
                    ctx = state.get("context") or {}
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
                    action_result = str(result.output or result.error or "Success")
                except Exception as e:
                    action_result = f"Error: {str(e)}"
            else:
                action_result = f"Tool not found: {action_name}"
        elif action_name:
            action_result = f"Action: {action_name}"
        else:
            action_result = "No action to execute"

        state["action"] = action_name
        state["observation"] = action_result
        return NodeResult(
            success=True,
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
                logging.debug(str(e), exc_info=True)

        obs = str(state.get("observation", "") or "")
        step_count = int(state.get("step_count", 0) or 0)
        max_steps_local = int(state.get("max_steps", max_steps) or max_steps)
        if "DONE" in obs.upper() or step_count >= max_steps_local:
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
    if "ACTION:" in reasoning.upper():
        parts = reasoning.upper().split("ACTION:")
        if len(parts) > 1:
            return parts[1].strip().split()[0]
    return None
