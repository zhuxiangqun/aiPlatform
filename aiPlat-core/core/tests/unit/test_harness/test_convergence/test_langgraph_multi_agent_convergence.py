import asyncio

from core.harness.execution.langgraph.graphs.multi_agent import MultiAgentGraph, MultiAgentConfig


def test_langgraph_multi_agent_evaluate_uses_detector():
    g = MultiAgentGraph(MultiAgentConfig(num_agents=0, convergence_threshold=1.0, max_rounds=3))
    state = {
        "task": "t",
        "agent_results": [{"result": "A"}, {"result": "A"}],
        "current_round": 1,
        "converged": False,
        "context": {},
    }
    out = asyncio.run(g._evaluate_convergence(state))
    assert out["converged"] is True
    assert out["final_result"] == "A"

