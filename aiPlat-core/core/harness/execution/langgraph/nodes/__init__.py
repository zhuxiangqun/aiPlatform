"""
LangGraph Nodes Module

Provides node registry infrastructure for LangGraph graphs.

Phase 9: ReasonNode/ActNode/ObserveNode retired — syscall logic inlined
into compiled_graphs/react.py. Only registry infrastructure remains.
"""

from .registry import (
    NodeDefinition,
    NodeRegistry,
    get_node_registry,
    register_node,
)

__all__ = [
    "NodeDefinition",
    "NodeRegistry",
    "get_node_registry",
    "register_node",
]