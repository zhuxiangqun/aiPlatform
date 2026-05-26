"""
MCP Protocol Integration — Layer 1 (core)

OWNERSHIP: aiPlat-core is the single owner of all MCP capability.
Transport, protocol, tool adapter, server, and client are all managed here.
The previous aiPlat-infra/infra/mcp layer was consolidated into this module
(2026-05) — no duplicate exists in any other layer.

Provides Model Context Protocol support for connecting to external tools
and exposing local tools via MCP.
"""

from .types import (
    JSONRPCVersion,
    TransportType,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPTool,
    MCPToolResult,
    MCPResource,
    MCPServerCapabilities,
    MCPInitializeResult,
    MCPServerConfig,
    MCPClientConfig,
    MCPResourceContent,
)

from .protocol import (
    MCPProtocolHandler,
    SSEHandler,
    StdioHandler,
)

from .client import (
    MCPClient,
    MCPClientManager,
)

from .adapter import (
    MCPToolAdapter,
    MCPToolExporter,
    MCPClientWrapper,
)

from .server import (
    MCPServer,
    create_mcp_server,
)

from .config import (
    MCPConfig,
    load_mcp_config,
    save_mcp_config,
)


__all__ = [
    # Types
    "JSONRPCVersion",
    "TransportType",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "MCPTool",
    "MCPToolResult",
    "MCPResource",
    "MCPServerCapabilities",
    "MCPInitializeResult",
    "MCPServerConfig",
    "MCPClientConfig",
    "MCPResourceContent",
    # Protocol
    "MCPProtocolHandler",
    "SSEHandler",
    "StdioHandler",
    # Client
    "MCPClient",
    "MCPClientManager",
    # Adapter
    "MCPToolAdapter",
    "MCPToolExporter",
    "MCPClientWrapper",
    # Server
    "MCPServer",
    "create_mcp_server",
    # Config
    "MCPConfig",
    "load_mcp_config",
    "save_mcp_config",
]