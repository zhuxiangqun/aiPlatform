import pytest


@pytest.mark.asyncio
async def test_agent_manager_loads_directory_agents_when_seed_false(tmp_path, monkeypatch):
    base = tmp_path / "agents"
    ad = base / "hello_agent"
    ad.mkdir(parents=True)
    (ad / "AGENT.md").write_text(
        "---\nname: hello_agent\n"
        "display_name: HelloAgent\n"
        "description: test\n"
        "agent_type: react\n"
        "version: 0.1.0\n"
        "status: ready\n"
        "required_skills: []\n"
        "required_tools: []\n"
        "config: {model: gpt-4}\n"
        "---\n\n# SOP\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_ENGINE_AGENTS_PATH", str(base))

    from core.management.agent_manager import AgentManager

    mgr = AgentManager(seed=False, scope="engine")
    agents = await mgr.list_agents()
    assert len(agents) == 1
    assert agents[0].id == "hello_agent"
    assert agents[0].name == "HelloAgent"
