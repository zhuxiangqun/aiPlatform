"""
Agent Discovery Module

Provides automatic agent discovery by scanning directories and parsing AGENT.md metadata.
"""

import os
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import yaml
import re


@dataclass
class DiscoveredAgent:
    """Discovered agent metadata"""
    name: str
    description: str
    display_name: str = ""
    version: str = "1.0.0"
    agent_type: str = "base"
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    supported_loop_types: List[str] = field(default_factory=list)
    required_skills: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    handler_path: Optional[str] = None
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name


class AGENTMD_PARSER:
    """Parser for AGENT.md format"""
    
    FRONT_MATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
    YAML_BLOCK_PATTERN = re.compile(r'```yaml\s*\n(.*?)```', re.DOTALL)
    
    @staticmethod
    def parse(agent_dir: Path) -> Optional[DiscoveredAgent]:
        """Parse AGENT.md file in agent directory"""
        agent_md = agent_dir / "AGENT.md"
        if not agent_md.exists():
            return None
        
        content = agent_md.read_text(encoding='utf-8')
        
        yaml_content = None
        
        match = AGENTMD_PARSER.FRONT_MATTER_PATTERN.match(content)
        if match:
            yaml_content = match.group(1)
        else:
            match = AGENTMD_PARSER.YAML_BLOCK_PATTERN.search(content)
            if match:
                yaml_content = match.group(1)
        
        if not yaml_content:
            lines = content.split('\n')
            yaml_lines = []
            in_yaml = False
            for line in lines:
                if line.strip().startswith('name:'):
                    in_yaml = True
                if in_yaml:
                    yaml_lines.append(line)
                    if line.strip() == '```' or (line.strip() and not line.startswith(' ') and not line.startswith('\t')) and len(yaml_lines) > 2:
                        break
            yaml_content = '\n'.join(yaml_lines)
        
        if not yaml_content:
            return None
        
        try:
            data = yaml.safe_load(yaml_content)
            if not data:
                return None
            
            return DiscoveredAgent(
                name=data.get('name', agent_dir.name),
                display_name=data.get('display_name', data.get('name', agent_dir.name)),
                description=data.get('description', ''),
                version=data.get('version', '1.0.0'),
                agent_type=data.get('agent_type', 'base'),
                tags=data.get('tags', []),
                capabilities=data.get('capabilities', []),
                supported_loop_types=data.get('supported_loop_types', ['react']),
                required_skills=data.get('required_skills', []),
                required_tools=data.get('required_tools', []),
                config_schema=data.get('config_schema', {}),
                examples=data.get('examples', []),
            )
        except yaml.YAMLError:
            return None


class AgentDiscovery:
    """
    Automatic agent discovery system.
    
    Scans directories to find and load agents with AGENT.md metadata.
    """
    
    def __init__(self, base_path: str):
        """
        Initialize discovery system.
        
        Args:
            base_path: Base directory to scan for agents
        """
        self.base_path = Path(base_path)
        self._parser = AGENTMD_PARSER()
        self._discovered: Dict[str, DiscoveredAgent] = {}
    
    async def discover(self) -> Dict[str, DiscoveredAgent]:
        """
        Scan directory and discover all agents.
        
        Returns:
            Dict mapping agent name to discovered metadata
        """
        if not self.base_path.exists():
            return {}
        
        self._discovered = {}
        
        for item in self.base_path.iterdir():
            if not item.is_dir():
                continue
            
            if item.name.startswith('.') or item.name in ['__pycache__']:
                continue
            
            agent_info = self._parser.parse(item)
            if agent_info:
                agent_info.handler_path = str(item / "agent.py")
                self._discovered[agent_info.name] = agent_info
        
        return self._discovered
    
    def get(self, name: str) -> Optional[DiscoveredAgent]:
        """Get discovered agent by name"""
        return self._discovered.get(name)
    
    def list_by_type(self, agent_type: str) -> List[DiscoveredAgent]:
        """List agents by type"""
        return [a for a in self._discovered.values() if a.agent_type == agent_type]
    
    def list_types(self) -> List[str]:
        """List all available agent types"""
        return list(set(a.agent_type for a in self._discovered.values()))
    
    def load_handler(self, agent_info: DiscoveredAgent):
        """Load agent handler module"""
        if not agent_info.handler_path:
            return None
        
        handler_path = Path(agent_info.handler_path)
        if not handler_path.exists():
            return None
        
        spec = importlib.util.spec_from_file_location(
            f"agent_{agent_info.name}",
            str(handler_path)
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        
        return None


class AgentLoader:
    """
    Agent loader with caching.
    
    Loads agent implementations on-demand.
    """
    
    def __init__(self, discovery: AgentDiscovery):
        self._discovery = discovery
        self._handlers: Dict[str, Any] = {}
    
    def load_handler(self, agent_name: str):
        """Load and cache agent handler"""
        if agent_name in self._handlers:
            return self._handlers[agent_name]
        
        agent_info = self._discovery.get(agent_name)
        if not agent_info:
            return None
        
        handler = self._discovery.load_handler(agent_info)
        if handler:
            self._handlers[agent_name] = handler
        
        return handler
    
    def get_agent_class(self, agent_name: str):
        """Get agent class from handler module"""
        handler = self.load_handler(agent_name)
        if not handler:
            return None
        
        for attr_name in dir(handler):
            attr = getattr(handler, attr_name)
            if isinstance(attr, type) and issubclass(attr, object):
                if attr_name.endswith('Agent') and attr_name != 'Agent':
                    return attr
        
        return None


def create_agent_discovery(base_path: str) -> AgentDiscovery:
    """Factory function to create agent discovery"""
    return AgentDiscovery(base_path)


def create_agent_loader(discovery: AgentDiscovery) -> AgentLoader:
    """Factory function to create agent loader"""
    return AgentLoader(discovery)


class AgentRegistry:
    """
    Agent registry for runtime management.
    
    Manages agent instances, their configurations, and states.
    """
    
    def __init__(self):
        self._agents: Dict[str, Any] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._states: Dict[str, str] = {}
        self._metadata: Dict[str, DiscoveredAgent] = {}
    
    def register(self, name: str, agent: Any, config: Dict[str, Any], metadata: Optional[DiscoveredAgent] = None):
        """Register an agent instance"""
        self._agents[name] = agent
        self._configs[name] = config
        self._states[name] = "idle"
        if metadata:
            self._metadata[name] = metadata
    
    def unregister(self, name: str):
        """Unregister an agent"""
        self._agents.pop(name, None)
        self._configs.pop(name, None)
        self._states.pop(name, None)
        self._metadata.pop(name, None)
    
    def get(self, name: str) -> Optional[Any]:
        """Get agent by name"""
        return self._agents.get(name)
    
    def list_all(self) -> List[str]:
        """List all registered agent names"""
        return list(self._agents.keys())
    
    def update_state(self, name: str, state: str):
        """Update agent state"""
        if name in self._agents:
            self._states[name] = state
    
    def get_state(self, name: str) -> Optional[str]:
        """Get agent state"""
        return self._states.get(name)
    
    def get_config(self, name: str) -> Optional[Dict[str, Any]]:
        """Get agent config"""
        return self._configs.get(name)
    
    def get_metadata(self, name: str) -> Optional[DiscoveredAgent]:
        """Get agent metadata"""
        return self._metadata.get(name)
    
    def list_by_state(self, state: str) -> List[str]:
        """List agents by state"""
        return [name for name, s in self._states.items() if s == state]


_global_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """Get global agent registry"""
    global _global_registry
    if _global_registry is None:
        _global_registry = AgentRegistry()
    return _global_registry