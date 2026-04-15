"""
ITool Interface - Tool Contract Definition
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class ToolSchema:
    """Tool parameter schema definition"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    returns: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolConfig:
    """Tool configuration"""
    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 30
    retry: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Tool execution result"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    latency: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ITool(ABC):
    """
    Tool Interface - Core contract for tool implementations
    
    Defines the minimum contract that all tool implementations must follow.
    """

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute tool with given parameters
        
        Args:
            params: Tool execution parameters
            
        Returns:
            ToolResult: Execution result
        """
        pass

    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate tool parameters
        
        Args:
            params: Parameters to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        pass

    @abstractmethod
    def get_schema(self) -> ToolSchema:
        """
        Get tool parameter schema
        
        Returns:
            ToolSchema: Tool schema
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """
        Get tool name
        
        Returns:
            str: Tool name
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        Get tool description
        
        Returns:
            str: Tool description
        """
        pass