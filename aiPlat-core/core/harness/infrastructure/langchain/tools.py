"""
LangChain Integration - Tools Module
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import inspect


@dataclass
class ToolDefinition:
    """Tool definition"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    func: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IToolWrapper(ABC):
    """
    Tool wrapper interface - Contract for tool wrappers
    """

    @abstractmethod
    def get_langchain_tool(self):
        """Get LangChain tool representation"""
        pass

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """Get tool definition"""
        pass


class FunctionToolWrapper(IToolWrapper):
    """
    Wraps a Python function as a LangChain tool
    """

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: Optional[Dict[str, Any]] = None
    ):
        self._name = name
        self._description = description
        self._func = func
        self._parameters = parameters or self._extract_parameters(func)

    def _extract_parameters(self, func: Callable) -> Dict[str, Any]:
        """Extract parameters from function signature"""
        sig = inspect.signature(func)
        params = {}
        
        for name, param in sig.parameters.items():
            param_info = {
                "type": "string",
                "description": f"Parameter {name}"
            }
            
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_info["type"] = "integer"
                elif param.annotation == float:
                    param_info["type"] = "number"
                elif param.annotation == bool:
                    param_info["type"] = "boolean"
            
            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default
            
            params[name] = param_info
        
        return params

    def get_langchain_tool(self):
        from langchain.tools import FunctionTool
        
        async def async_func(**kwargs):
            if inspect.iscoroutinefunction(self._func):
                return await self._func(**kwargs)
            return self._func(**kwargs)
        
        return FunctionTool(
            name=self._name,
            description=self._description,
            args_schema=self._create_schema(),
            func=async_func,
        )

    def _create_schema(self):
        from pydantic import BaseModel
        
        class ToolSchema(BaseModel):
            pass
        
        for name, info in self._parameters.items():
            setattr(ToolSchema, name, field(default=info.get("default")))
        
        return ToolSchema

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters=self._parameters,
            func=self._func,
        )


class StructuredToolWrapper(IToolWrapper):
    """
    Wraps a structured tool with input/output schemas
    """

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        output_schema: Dict[str, Any],
        func: Callable
    ):
        self._name = name
        self._description = description
        self._input_schema = input_schema
        self._output_schema = output_schema
        self._func = func

    def get_langchain_tool(self):
        from langchain.tools import StructuredTool
        
        async def async_func(**kwargs):
            if inspect.iscoroutinefunction(self._func):
                return await self._func(**kwargs)
            return self._func(**kwargs)
        
        return StructuredTool(
            name=self._name,
            description=self._description,
            args_schema=self._create_input_schema(),
            func=async_func,
        )

    def _create_schema(self):
        from pydantic import BaseModel, Field
        
        class InputSchema(BaseModel):
            pass
        
        for name, info in self._input_schema.items():
            field_info = Field(description=info.get("description", ""))
            if "default" in info:
                field_info.default = info["default"]
            setattr(InputSchema, name, field_info)
        
        return InputSchema

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters=self._input_schema,
            func=self._func,
        )


def create_tool_from_function(
    func: Callable,
    name: Optional[str] = None,
    description: Optional[str] = None
) -> IToolWrapper:
    """
    Factory function to create tool wrapper from function
    
    Args:
        func: Python function to wrap
        name: Tool name (defaults to function name)
        description: Tool description
        
    Returns:
        IToolWrapper: Tool wrapper instance
    """
    tool_name = name or func.__name__
    tool_desc = description or func.__doc__ or f"Tool {tool_name}"
    
    return FunctionToolWrapper(
        name=tool_name,
        description=tool_desc,
        func=func,
    )


def create_tool_from_class(
    cls: type,
    name: Optional[str] = None,
    description: Optional[str] = None
) -> IToolWrapper:
    """
    Factory function to create tool wrapper from class
    
    Args:
        cls: Python class to wrap
        name: Tool name
        description: Tool description
        
    Returns:
        IToolWrapper: Tool wrapper instance
    """
    tool_name = name or cls.__name__
    tool_desc = description or cls.__doc__ or f"Tool {tool_name}"
    
    return StructuredToolWrapper(
        name=tool_name,
        description=tool_desc,
        input_schema={"input": {"type": "string", "description": "Input text"}},
        output_schema={"output": {"type": "string", "description": "Output text"}},
        func=cls(),
    )