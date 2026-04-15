"""
Apps Module

Provides application layer: Agents, Skills, Tools implementations.
"""

from .agents import (
    BaseAgent,
    ConfigurableAgent,
    ReActAgent,
    PlanExecuteAgent,
    ConversationalAgent,
    MultiAgent,
    create_agent,
    create_react_agent,
    create_conversational_agent,
    create_multi_agent,
)

from .skills import (
    BaseSkill,
    TextGenerationSkill,
    CodeGenerationSkill,
    DataAnalysisSkill,
    SkillRegistry,
    get_skill_registry,
    create_skill,
)

from .tools import (
    BaseTool,
    CalculatorTool,
    SearchTool,
    FileOperationsTool,
    ToolRegistry,
    get_tool_registry,
    create_tool,
)

from .mcp import (
    MCPClient,
    MCPClientManager,
    MCPToolAdapter,
    create_mcp_server,
    load_mcp_config,
    MCPConfig,
)

from .quality import (
    QualityGate,
    SecurityScanner,
    ResultVerifier,
    create_quality_gate,
    create_security_scanner,
    create_verifier,
    QualityGateResult,
    SecurityScanResult,
    VerificationResult,
)

__all__ = [
    # Agents
    "BaseAgent",
    "ConfigurableAgent",
    "ReActAgent",
    "PlanExecuteAgent",
    "ConversationalAgent",
    "MultiAgent",
    "create_agent",
    "create_react_agent",
    "create_conversational_agent",
    "create_multi_agent",
    
    # Skills
    "BaseSkill",
    "TextGenerationSkill",
    "CodeGenerationSkill",
    "DataAnalysisSkill",
    "SkillRegistry",
    "get_skill_registry",
    "create_skill",
    
    # Tools
    "BaseTool",
    "CalculatorTool",
    "SearchTool",
    "FileOperationsTool",
    "ToolRegistry",
    "get_tool_registry",
    "create_tool",
    
    # MCP
    "MCPClient",
    "MCPClientManager",
    "MCPToolAdapter",
    "create_mcp_server",
    "load_mcp_config",
    "MCPConfig",
    
    # Quality
    "QualityGate",
    "SecurityScanner",
    "ResultVerifier",
    "create_quality_gate",
    "create_security_scanner",
    "create_verifier",
    "QualityGateResult",
    "SecurityScanResult",
    "VerificationResult",
]