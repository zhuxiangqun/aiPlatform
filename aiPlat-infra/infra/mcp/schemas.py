from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Tool:
    name: str = ""
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    content: Any = None
    is_error: bool = False


@dataclass
class Resource:
    uri: str = ""
    name: str = ""
    mime_type: str = ""


@dataclass
class ResourceContent:
    uri: str = ""
    mime_type: str = ""
    content: Any = None


@dataclass
class MCPConfig:
    type: str = "stdio"
    server_command: Optional[List[str]] = None
    server_url: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 1
