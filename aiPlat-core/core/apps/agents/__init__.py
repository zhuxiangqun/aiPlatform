"""
Agents Module

Provides agent implementations: Base, ReAct, Plan-Execute, Conversational, Multi-Agent, RAG,
with automatic discovery system and registry.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

__all__ = [
    # Base
    "BaseAgent",
    "ConfigurableAgent",
    "AgentMetadata",
    "create_agent",
    
    # ReAct
    "ReActAgent",
    "ReActAgentConfig",
    "create_react_agent",
    
    # Plan-Execute
    "PlanExecuteAgent",
    "PlanExecuteAgentConfig",
    "PlanStep",
    "create_plan_execute_agent",
    
    # Conversational
    "ConversationalAgent",
    "ConversationalAgentConfig",
    "create_conversational_agent",
    
    # Multi-Agent
    "MultiAgent",
    "MultiAgentConfig",
    "AgentSpec",
    "SwarmAgent",
    "create_multi_agent",
    
    # RAG
    "RAGAgent",
    "RAGConfig",
    "create_rag_agent",
    
    # Discovery
    "DiscoveredAgent",
    "AGENTMD_PARSER",
    "AgentDiscovery",
    "AgentLoader",
    "AgentRegistry",
    "create_agent_discovery",
    "create_agent_loader",
    "get_agent_registry",
    
    # Subagent
    "SubagentConfig",
    "SubagentInstance",
    "SubagentRegistry",
    "SubagentCoordinator",
    "SubagentResult",
    "get_subagent_registry",
    "get_subagent_coordinator",
    "initialize_registry",
    "BUILTIN_SUBAGENTS",
]


# Avoid eager imports to reduce circular dependencies (agents <-> execution/langgraph/syscalls).
_CANDIDATE_SUBMODULES = (
    "base",
    "react",
    "plan_execute",
    "conversational",
    "multi_agent",
    "rag",
    "discovery",
    "subagent",
)


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    for mod in _CANDIDATE_SUBMODULES:
        m = importlib.import_module(f"{__name__}.{mod}")
        if hasattr(m, name):
            return getattr(m, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))


if TYPE_CHECKING:
    from .base import AgentMetadata, BaseAgent, ConfigurableAgent, create_agent
    from .conversational import ConversationalAgent, ConversationalAgentConfig, create_conversational_agent
    from .discovery import (
        AGENTMD_PARSER,
        AgentDiscovery,
        AgentLoader,
        AgentRegistry,
        DiscoveredAgent,
        create_agent_discovery,
        create_agent_loader,
        get_agent_registry,
    )
    from .multi_agent import AgentSpec, MultiAgent, MultiAgentConfig, SwarmAgent, create_multi_agent
    from .plan_execute import PlanExecuteAgent, PlanExecuteAgentConfig, PlanStep, create_plan_execute_agent
    from .rag import RAGAgent, RAGConfig, create_rag_agent
    from .react import ReActAgent, ReActAgentConfig, create_react_agent
    from .subagent import (
        BUILTIN_SUBAGENTS,
        SubagentConfig,
        SubagentCoordinator,
        SubagentInstance,
        SubagentRegistry,
        SubagentResult,
        get_subagent_coordinator,
        get_subagent_registry,
        initialize_registry,
    )
