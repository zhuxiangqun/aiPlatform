import asyncio

from core.harness.state import AgentStateEnum
from core.management.agent_manager import AgentManager


def test_agent_manager_uses_canonical_status_values():
    mgr = AgentManager(seed=False)

    # create_agent should start as INITIALIZING
    agent = asyncio.run(
        mgr.create_agent(
            name="My Agent",
            agent_type="react",
            config={"model": "gpt-4"},
        )
    )
    assert agent.status == AgentStateEnum.INITIALIZING.value

    # start/stop should use RUNNING/STOPPED
    assert asyncio.run(mgr.start_agent(agent.id)) is True
    assert asyncio.run(mgr.get_agent(agent.id)).status == AgentStateEnum.RUNNING.value

    assert asyncio.run(mgr.stop_agent(agent.id)) is True
    assert asyncio.run(mgr.get_agent(agent.id)).status == AgentStateEnum.STOPPED.value
