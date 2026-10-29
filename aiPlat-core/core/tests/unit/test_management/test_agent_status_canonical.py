import asyncio

from core.harness.state import AgentStateEnum
from core.management.agent_manager import AgentManager


def test_agent_manager_uses_canonical_status_values():
    mgr = AgentManager(seed=False)

    # create_agent: catalog status is ready (auto-smoke gates execute readiness)
    agent = asyncio.run(
        mgr.create_agent(
            name="My Agent",
            agent_type="react",
            config={"model": "gpt-4"},
        )
    )
    assert agent.status == AgentStateEnum.READY.value

    # start/stop update runtime_state (catalog status stays ready while enabled)
    assert asyncio.run(mgr.start_agent(agent.id)) is True
    started = asyncio.run(mgr.get_agent(agent.id))
    assert started.runtime_state == AgentStateEnum.RUNNING.value

    assert asyncio.run(mgr.stop_agent(agent.id)) is True
    stopped = asyncio.run(mgr.get_agent(agent.id))
    assert stopped.runtime_state == AgentStateEnum.STOPPED.value
