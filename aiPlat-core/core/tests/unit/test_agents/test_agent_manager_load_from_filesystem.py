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


@pytest.mark.asyncio
async def test_agent_manager_hoists_top_level_eval_profile_into_config(tmp_path, monkeypatch):
    """AGENT.md top-level eval_profile → AgentInfo.config (object-contract)."""
    base = tmp_path / "agents"
    ad = base / "profile_agent"
    ad.mkdir(parents=True)
    (ad / "AGENT.md").write_text(
        "---\n"
        "name: profile_agent\n"
        "display_name: ProfileAgent\n"
        "description: eval_profile hoist\n"
        "agent_type: conversational\n"
        "version: 0.2.0\n"
        "status: ready\n"
        "required_skills: [chitchat]\n"
        "required_tools: []\n"
        "config:\n"
        "  model: gpt-4\n"
        "eval_profile:\n"
        "  capabilities: [clarify_or_ask, retrieval]\n"
        "  permissions: [read_only]\n"
        "  target_runtime: [workspace_execute]\n"
        "---\n\n# SOP\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_ENGINE_AGENTS_PATH", str(base))

    from core.management.agent_manager import AgentManager
    from core.apps.eval.service.eval_profile_resolve import build_eval_profile_from_declarations

    mgr = AgentManager(seed=False, scope="engine")
    agent = await mgr.get_agent("profile_agent")
    assert agent is not None
    ep = (agent.config or {}).get("eval_profile")
    assert isinstance(ep, dict)
    assert "clarify_or_ask" in ep["capabilities"]
    profile = build_eval_profile_from_declarations(
        skills=agent.skills,
        config=agent.config,
        object_version=agent.version,
    )
    assert profile["profile_source"] == "explicit"
    assert profile["capabilities"] == ["clarify_or_ask", "retrieval"]
