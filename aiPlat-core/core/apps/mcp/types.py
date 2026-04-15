"""
MCP Protocol Types

Defines the core data types for Model Context Protocol.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import json


class JSONRPCVersion(str, Enum):
    """JSON-RPC version"""
    V2_0 = "2.0"


class TransportType(str, Enum):
    """MCP transport types"""
    STDIO = "stdio"
    SSE = "sse"


@dataclass
class JSONRPCRequest:
    """JSON-RPC request message"""
    jsonrpc: JSONRPCVersion = JSONRPCVersion.V2_0
    method: str = ""
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None

    def to_json(self) -> str:
        return json.dumps({
            "jsonrpc": self.jsonrpc.value,
            "method": self.method,
            "params": self.params,
            "id": self.id
        })

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JSONRPCRequest":
        return cls(
            jsonrpc=JSONRPCVersion(data.get("jsonrpc", "2.0")),
            method=data.get("method", ""),
            params=data.get("params"),
            id=data.get("id")
        )


@dataclass
class JSONRPCResponse:
    """JSON-RPC response message"""
    jsonrpc: JSONRPCVersion = JSONRPCVersion.V2_0
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def to_json(self) -> str:
        data = {"jsonrpc": self.jsonrpc.value, "id": self.id}
        if self.error:
            data["error"] = self.error
        else:
            data["result"] = self.result
        return json.dumps(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JSONRPCResponse":
        return cls(
            jsonrpc=JSONRPCVersion(data.get("jsonrpc", "2.0")),
            result=data.get("result"),
            error=data.get("error"),
            id=data.get("id")
        )


@dataclass
class MCPTool:
    """MCP Tool definition"""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPToolResult:
    """MCP Tool call result"""
    content: str
    is_error: bool = False
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MCPResource:
    """MCP Resource definition"""
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass
class MCPServerCapabilities:
    """MCP Server capabilities"""
    tools: bool = True
    resources: bool = False
    prompts: bool = False


@dataclass
class MCPInitializeResult:
    """MCP initialize result"""
    protocol_version: str
    capabilities: MCPServerCapabilities
    server_info: Dict[str, str]


@dataclass
class MCPServerConfig:
    """MCP Server configuration"""
    name: str
    transport: TransportType = TransportType.SSE
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    url: Optional[str] = None
    auth: Optional[Dict[str, Any]] = None


@dataclass
class MCPClientConfig:
    """MCP Client configuration"""
    server_url: str
    transport: TransportType = TransportType.SSE
    timeout: int = 30000
    auth: Optional[Dict[str, Any]] = None