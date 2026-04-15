"""
Tools Module

Provides tool implementations: Base, Calculator, Search, FileOperations,
HTTP, Browser, Database, CodeExecution, WebFetch,
with registry, permission management, and hybrid recall system.
"""

from .base import (
    BaseTool,
    ToolMetadata,
    CalculatorTool,
    SearchTool,
    FileOperationsTool,
    ToolRegistry,
    get_tool_registry,
    create_tool,
)

from .permission import (
    Permission,
    PermissionEntry,
    PermissionManager,
    get_permission_manager,
    RoleBasedAccess,
    Role,
    ResourcePermission,
)

from .recaller import (
    RecallSource,
    RecallResult,
    TokenRecaller,
    RAGRecaller,
    NeuralEnhancer,
    ToolRecaller,
    get_tool_recaller,
)

from .http import HTTPClientTool
from .browser import BrowserTool
from .database import DatabaseTool
from .code import CodeExecutionTool
from .webfetch import WebFetchTool

__all__ = [
    # Base tools
    "BaseTool",
    "ToolMetadata",
    "CalculatorTool",
    "SearchTool",
    "FileOperationsTool",
    "ToolRegistry",
    "get_tool_registry",
    "create_tool",
    # Enhanced tools
    "HTTPClientTool",
    "BrowserTool",
    "DatabaseTool",
    "CodeExecutionTool",
    "WebFetchTool",
    # Permissions
    "Permission",
    "PermissionEntry",
    "PermissionManager",
    "get_permission_manager",
    "RoleBasedAccess",
    "Role",
    "ResourcePermission",
    # Recaller
    "RecallSource",
    "RecallResult",
    "TokenRecaller",
    "RAGRecaller",
    "NeuralEnhancer",
    "ToolRecaller",
    "get_tool_recaller",
]