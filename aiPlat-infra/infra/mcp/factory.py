from typing import Optional
from .schemas import MCPConfig
from .base import MCPClient


def create_mcp_client(config: Optional[MCPConfig] = None) -> MCPClient:
    config = config or MCPConfig()
    from .client import MCPClientImpl

    return MCPClientImpl(config)
