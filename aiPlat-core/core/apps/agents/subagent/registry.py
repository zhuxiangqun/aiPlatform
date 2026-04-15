"""
Subagent Registry

Manages Subagent registration and discovery.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

from .config import SubagentConfig, BUILTIN_SUBAGENTS

logger = logging.getLogger(__name__)


class SubagentRegistry:
    """Subagent registry for managing available Subagents"""
    
    def __init__(self):
        self._subagents: Dict[str, SubagentConfig] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize with built-in Subagents"""
        if self._initialized:
            return
        
        # Register built-in Subagents
        for name, config in BUILTIN_SUBAGENTS.items():
            self.register(config)
        
        self._initialized = True
        logger.info(f"Initialized Subagent registry with {len(self._subagents)} built-in subagents")
    
    def register(self, config: SubagentConfig):
        """Register a Subagent"""
        self._subagents[config.name] = config
        logger.info(f"Registered Subagent: {config.name}")
    
    def unregister(self, name: str) -> bool:
        """Unregister a Subagent"""
        if name in self._subagents:
            del self._subagents[name]
            logger.info(f"Unregistered Subagent: {name}")
            return True
        return False
    
    def get(self, name: str) -> Optional[SubagentConfig]:
        """Get Subagent config by name"""
        return self._subagents.get(name)
    
    def list_all(self) -> List[str]:
        """List all available Subagent names"""
        return list(self._subagents.keys())
    
    def find_by_capability(self, capability: str) -> List[SubagentConfig]:
        """Find Subagents by capability keyword"""
        results = []
        for config in self._subagents.values():
            if capability.lower() in config.description.lower():
                results.append(config)
        return results
    
    def find_by_tools(self, required_tools: List[str]) -> List[SubagentConfig]:
        """Find Subagents that have the required tools"""
        results = []
        for config in self._subagents.values():
            if all(config.can_use_tool(tool) for tool in required_tools):
                results.append(config)
        return results
    
    def get_stats(self) -> Dict:
        """Get registry statistics"""
        return {
            "total_subagents": len(self._subagents),
            "by_permission_level": self._count_by_permission_level()
        }
    
    def _count_by_permission_level(self) -> Dict[str, int]:
        counts = {}
        for config in self._subagents.values():
            level = config.permission_level.value
            counts[level] = counts.get(level, 0) + 1
        return counts


# Global registry instance
_global_registry: Optional[SubagentRegistry] = None


def get_subagent_registry() -> SubagentRegistry:
    """Get global Subagent registry"""
    global _global_registry
    if _global_registry is None:
        _global_registry = SubagentRegistry()
    return _global_registry


async def initialize_registry() -> SubagentRegistry:
    """Initialize and get registry"""
    registry = get_subagent_registry()
    await registry.initialize()
    return registry


__all__ = [
    "SubagentRegistry",
    "get_subagent_registry",
    "initialize_registry"
]