"""
LangGraph Node Registry

Central registry for all LangGraph nodes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type
import asyncio


@dataclass
class NodeDefinition:
    """Node definition"""
    name: str
    description: str
    handler: Callable
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class INodeRegistry(ABC):
    """
    Node registry interface
    """

    @abstractmethod
    def register(self, definition: NodeDefinition) -> None:
        """Register a node"""
        pass

    @abstractmethod
    def get(self, name: str) -> Optional[NodeDefinition]:
        """Get node by name"""
        pass

    @abstractmethod
    def list_nodes(self) -> List[str]:
        """List all node names"""
        pass


class NodeRegistry(INodeRegistry):
    """
    Default node registry implementation
    """

    def __init__(self):
        self._nodes: Dict[str, NodeDefinition] = {}

    def register(self, definition: NodeDefinition) -> None:
        """Register a node"""
        self._nodes[definition.name] = definition

    def get(self, name: str) -> Optional[NodeDefinition]:
        """Get node by name"""
        return self._nodes.get(name)

    def list_nodes(self) -> List[str]:
        """List all node names"""
        return list(self._nodes.keys())


# Global registry
_global_registry = NodeRegistry()


def get_node_registry() -> NodeRegistry:
    """Get global node registry"""
    return _global_registry


def register_node(
    name: str,
    description: str,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None
) -> Callable:
    """
    Decorator to register a node
    
    Usage:
        @register_node("reason", "Reasoning node")
        async def reason_node(state):
            return {"reasoning": "..."}
    """
    def decorator(func: Callable) -> Callable:
        definition = NodeDefinition(
            name=name,
            description=description,
            handler=func,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
        )
        _global_registry.register(definition)
        return func
    return decorator