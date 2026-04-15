"""
Agents Module

Provides agent implementations: Base, ReAct, Plan-Execute, Conversational, Multi-Agent, RAG,
with automatic discovery system and registry.
"""

from .base import (
    BaseAgent,
    ConfigurableAgent,
    AgentMetadata,
    create_agent,
)

from .react import (
    ReActAgent,
    ReActAgentConfig,
    create_react_agent,
)

from .plan_execute import (
    PlanExecuteAgent,
    PlanExecuteAgentConfig,
    PlanStep,
    create_plan_execute_agent,
)

from .conversational import (
    ConversationalAgent,
    ConversationalAgentConfig,
    create_conversational_agent,
)

from .multi_agent import (
    MultiAgent,
    MultiAgentConfig,
    AgentSpec,
    SwarmAgent,
    create_multi_agent,
)

from .rag import (
    RAGAgent,
    RAGConfig,
    create_rag_agent,
)

from .discovery import (
    DiscoveredAgent,
    AGENTMD_PARSER,
    AgentDiscovery,
    AgentLoader,
    AgentRegistry,
    create_agent_discovery,
    create_agent_loader,
    get_agent_registry,
)

from .subagent import (
    SubagentConfig,
    SubagentInstance,
    SubagentRegistry,
    SubagentCoordinator,
    SubagentResult,
    get_subagent_registry,
    get_subagent_coordinator,
    initialize_registry,
    BUILTIN_SUBAGENTS,
)

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