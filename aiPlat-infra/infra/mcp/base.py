from abc import ABC, abstractmethod
from typing import List, Optional
from .schemas import Tool, ToolResult, Resource, ResourceContent


class MCPClient(ABC):
    @abstractmethod
    async def connect(self, server_url: Optional[str] = None) -> None:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def list_tools(self) -> List[Tool]:
        pass

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict) -> ToolResult:
        pass

    @abstractmethod
    async def list_resources(self) -> List[Resource]:
        pass

    @abstractmethod
    async def read_resource(self, uri: str) -> ResourceContent:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass


class MCPTransport(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def send(self, method: str, params: dict = None) -> dict:
        pass
