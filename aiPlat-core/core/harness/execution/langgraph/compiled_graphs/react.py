"""
Compiled ReAct graph (Reason -> Act -> Observe) using internal CompiledGraph engine.

目的：
- 让 checkpoint/restore/resume 能在“不依赖外部 langgraph”路径上闭环。
- 触发 CallbackManager 事件，配合 server lifespan 的落库 handler 写入 ExecutionStore。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core import GraphBuilder, GraphConfig, NodeResult, CompiledGraph
from ..nodes import create_reason_node, create_act_node, create_observe_node


def create_compiled_react_graph(
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    max_steps: int = 10,
    graph_name: str = "compiled_react",
) -> CompiledGraph:
    builder = GraphBuilder(name=graph_name)

    reason_node = create_reason_node(model=model, tools=tools or [])
    act_node = create_act_node(model=model, tools=tools or [])
    observe_node = create_observe_node(model=model, tools=tools or [])

    async def reason(state: Dict[str, Any]) -> NodeResult:
        updates = await reason_node.execute(state)  # type: ignore[arg-type]
        if isinstance(updates, dict):
            # CompiledGraph engine already increments step_count; avoid double increment
            updates.pop("step_count", None)
            state.update(updates)
        # If model says DONE, short-circuit (no tool execution)
        reasoning = str(state.get("reasoning", "") or "")
        if "DONE" in reasoning.upper():
            state["observation"] = "DONE"
            return NodeResult(success=True, output=updates, next_node=None)
        return NodeResult(success=True, output=updates, next_node="act")

    async def act(state: Dict[str, Any]) -> NodeResult:
        updates = await act_node.execute(state)  # type: ignore[arg-type]
        if isinstance(updates, dict):
            state.update(updates)
        return NodeResult(success=True, output=updates, next_node="observe")

    async def observe(state: Dict[str, Any]) -> NodeResult:
        updates = await observe_node.execute(state)  # type: ignore[arg-type]
        if isinstance(updates, dict):
            state.update(updates)
        obs = str(state.get("observation", "") or "")
        step_count = int(state.get("step_count", 0) or 0)
        max_steps_local = int(state.get("max_steps", max_steps) or max_steps)
        if "DONE" in obs.upper() or step_count >= max_steps_local:
            return NodeResult(success=True, output=updates, next_node=None)
        return NodeResult(success=True, output=updates, next_node="reason")

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
