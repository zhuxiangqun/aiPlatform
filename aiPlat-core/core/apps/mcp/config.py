"""
MCP Configuration

Configuration management for MCP servers and clients.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import yaml
from pathlib import Path

from .types import MCPServerConfig, MCPClientConfig, TransportType


@dataclass
class MCPConfig:
    """MCP configuration"""
    servers: List[MCPServerConfig] = field(default_factory=list)
    clients: List[MCPClientConfig] = field(default_factory=list)


def load_mcp_config(config_path: str) -> MCPConfig:
    """Load MCP configuration from YAML file"""
    path = Path(config_path)
    
    if not path.exists():
        return MCPConfig()
        
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        
    servers = []
    clients = []
    
    # Parse servers
    for server_data in data.get("servers", []):
        servers.append(MCPServerConfig(
            name=server_data["name"],
            transport=TransportType(server_data.get("transport", "sse")),
            command=server_data.get("command"),
            args=server_data.get("args", []),
            url=server_data.get("url"),
            auth=server_data.get("auth")
        ))
        
    # Parse clients
    for client_data in data.get("clients", []):
        clients.append(MCPClientConfig(
            server_url=client_data["server_url"],
            transport=TransportType(client_data.get("transport", "sse")),
            timeout=client_data.get("timeout", 30000),
            auth=client_data.get("auth")
        ))
        
    return MCPConfig(servers=servers, clients=clients)


def save_mcp_config(config: MCPConfig, config_path: str) -> None:
    """Save MCP configuration to YAML file"""
    data = {
        "servers": [],
        "clients": []
    }
    
    for server in config.servers:
        server_dict = {
            "name": server.name,
            "transport": server.transport.value
        }
        if server.command:
            server_dict["command"] = server.command
        if server.args:
            server_dict["args"] = server.args
        if server.url:
            server_dict["url"] = server.url
        if server.auth:
            server_dict["auth"] = server.auth
        data["servers"].append(server_dict)
        
    for client in config.clients:
        client_dict = {
            "server_url": client.server_url,
            "transport": client.transport.value,
            "timeout": client.timeout
        }
        if client.auth:
            client_dict["auth"] = client.auth
        data["clients"].append(client_dict)
        
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)