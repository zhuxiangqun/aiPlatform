import pytest

from core.harness.execution.langgraph.core import GraphBuilder, NodeResult, GraphConfig


@pytest.mark.asyncio
async def test_compiled_graph_can_resume_from_state_current_node():
    builder = GraphBuilder(name="resume_test")

    async def node_a(state):
        state["context"] = state.get("context") or {}
        state["context"]["a"] = True
        return NodeResult(success=True, output="a", next_node="b")

    async def node_b(state):
        state["context"]["b"] = True
        return NodeResult(success=True, output="b", next_node=None)

    graph = (
        builder.add_node("a", node_a)
        .add_node("b", node_b)
        .add_edge("a", "b")
        .set_entry_point("a")
        .add_end_point("b")
        .build()
    )

    # First run: stop after node a by limiting max_steps=1, and let "b" be next current_node.
    state1 = await graph.execute(
        {"messages": [], "context": {}},
        config=GraphConfig(max_steps=1, enable_checkpoints=True, checkpoint_interval=1, enable_callbacks=False),
    )
    assert state1["context"]["a"] is True
    assert state1.get("current_node") == "b"

    # Resume: start from current_node="b" and continue
    state2 = await graph.execute(
        state1,
        config=GraphConfig(max_steps=3, enable_checkpoints=False, enable_callbacks=False),
    )
    assert state2["context"]["b"] is True

