import pytest
import tempfile
from pathlib import Path
from core.apps.agents import (
    AgentDiscovery,
    AgentLoader,
    AgentRegistry,
    DiscoveredAgent,
    AGENTMD_PARSER,
)


class TestAgentMetadata:
    """Test DiscoveredAgent with extended fields"""
    
    def test_basic_fields(self):
        agent = DiscoveredAgent(
            name="react_agent",
            description="ReAct agent description"
        )
        assert agent.name == "react_agent"
        assert agent.description == "ReAct agent description"
        assert agent.version == "1.0.0"
        assert agent.agent_type == "base"
    
    def test_extended_fields(self):
        agent = DiscoveredAgent(
            name="react_agent",
            display_name="ReAct Agent",
            description="ReAct agent for reasoning",
            agent_type="react",
            capabilities=["reasoning", "tool_use"],
            supported_loop_types=["react", "react-json"],
            required_skills=["text_generation"],
            required_tools=["web_search", "calculator"]
        )
        assert agent.display_name == "ReAct Agent"
        assert agent.agent_type == "react"
        assert agent.capabilities == ["reasoning", "tool_use"]
        assert agent.supported_loop_types == ["react", "react-json"]
        assert agent.required_skills == ["text_generation"]
        assert agent.required_tools == ["web_search", "calculator"]


class TestAGENTMDParser:
    """Test AGENT.md parser"""
    
    def test_parse_front_matter(self, tmp_path):
        agent_dir = tmp_path / "react_agent"
        agent_dir.mkdir()
        
        agent_md = agent_dir / "AGENT.md"
        agent_md.write_text("""---
name: react_agent
display_name: ReAct Agent
description: Reasoning and Acting agent
version: 1.0.0
agent_type: react
tags: [reasoning, tool-use]
capabilities:
  - Multi-step reasoning
  - Tool execution
supported_loop_types:
  - react
  - react-json
required_skills:
  - text_generation
required_tools:
  - web_search
  - calculator
---
""")
        
        parser = AGENTMD_PARSER()
        result = parser.parse(agent_dir)
        
        assert result is not None
        assert result.name == "react_agent"
        assert result.display_name == "ReAct Agent"
        assert result.agent_type == "react"
        assert result.capabilities == ["Multi-step reasoning", "Tool execution"]
        assert result.required_skills == ["text_generation"]
        assert result.required_tools == ["web_search", "calculator"]
    
    def test_parse_no_file(self, tmp_path):
        agent_dir = tmp_path / "empty"
        agent_dir.mkdir()
        
        parser = AGENTMD_PARSER()
        result = parser.parse(agent_dir)
        
        assert result is None


class TestAgentDiscovery:
    """Test agent discovery system"""
    
    @pytest.mark.asyncio
    async def test_discover_empty_dir(self, tmp_path):
        discovery = AgentDiscovery(str(tmp_path))
        result = await discovery.discover()
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_discover_with_agents(self, tmp_path):
        agent_dir = tmp_path / "react_agent"
        agent_dir.mkdir()
        
        agent_md = agent_dir / "AGENT.md"
        agent_md.write_text("""---
name: react_agent
description: ReAct agent
agent_type: react
---
""")
        
        discovery = AgentDiscovery(str(tmp_path))
        result = await discovery.discover()
        
        assert "react_agent" in result
        agent_info = result["react_agent"]
        assert agent_info.name == "react_agent"
        assert agent_info.agent_type == "react"
    
    @pytest.mark.asyncio
    async def test_list_by_type(self, tmp_path):
        (tmp_path / "agent1").mkdir()
        (tmp_path / "agent1").joinpath("AGENT.md").write_text("""---
name: agent1
agent_type: react
---
""")
        
        (tmp_path / "agent2").mkdir()
        (tmp_path / "agent2").joinpath("AGENT.md").write_text("""---
name: agent2
agent_type: planning
---
""")
        
        discovery = AgentDiscovery(str(tmp_path))
        await discovery.discover()
        
        react_agents = discovery.list_by_type("react")
        assert len(react_agents) == 1
        assert react_agents[0].name == "agent1"
    
    @pytest.mark.asyncio
    async def test_list_types(self, tmp_path):
        (tmp_path / "agent1").mkdir()
        (tmp_path / "agent1").joinpath("AGENT.md").write_text("""---
name: agent1
agent_type: react
---
""")
        
        (tmp_path / "agent2").mkdir()
        (tmp_path / "agent2").joinpath("AGENT.md").write_text("""---
name: agent2
agent_type: planning
---
""")
        
        discovery = AgentDiscovery(str(tmp_path))
        await discovery.discover()
        
        types = discovery.list_types()
        assert "react" in types
        assert "planning" in types


class TestAgentRegistry:
    """Test agent registry"""
    
    def test_register_unregister(self):
        registry = AgentRegistry()
        
        registry.register("test-agent", "agent-instance", {"key": "value"})
        
        assert "test-agent" in registry.list_all()
        assert registry.get("test-agent") == "agent-instance"
        assert registry.get_config("test-agent") == {"key": "value"}
        
        registry.unregister("test-agent")
        assert "test-agent" not in registry.list_all()
    
    def test_update_state(self):
        registry = AgentRegistry()
        
        registry.register("test-agent", "agent-instance", {})
        registry.update_state("test-agent", "running")
        
        assert registry.get_state("test-agent") == "running"
    
    def test_list_by_state(self):
        registry = AgentRegistry()
        
        registry.register("agent1", "instance1", {})
        registry.register("agent2", "instance2", {})
        
        registry.update_state("agent1", "running")
        registry.update_state("agent2", "idle")
        
        running = registry.list_by_state("running")
        assert "agent1" in running
        assert "agent2" not in running


class TestAgentLoader:
    """Test agent loader with caching"""
    
    def test_registration(self):
        registry = AgentRegistry()
        
        registry.register("agent1", "instance1", {"type": "react"})
        
        assert registry.get("agent1") == "instance1"
        assert registry.get_config("agent1") == {"type": "react"}