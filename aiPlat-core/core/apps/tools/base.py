"""
Tool Base Module

Provides base Tool class implementing ITool interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import asyncio
import time

from ...harness.interfaces import (
    ITool,
    ToolConfig,
    ToolSchema,
    ToolResult,
)


@dataclass
class ToolMetadata:
    """Tool metadata"""
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"
    tags: List[str] = field(default_factory=list)


class BaseTool(ITool):
    """
    Base Tool Implementation
    
    Provides common functionality for all tool implementations.
    """

    def __init__(self, config: ToolConfig):
        self._config = config
        self._stats = {
            "call_count": 0,
            "success_count": 0,
            "error_count": 0,
            "total_latency": 0.0,
            "avg_latency": 0.0
        }

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute tool - to be implemented by subclass"""
        raise NotImplementedError("Subclass must implement execute")

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate parameters"""
        # Check required parameters
        required = self._config.parameters.get("required", [])
        
        for param in required:
            if param not in params:
                return False
        
        return True

    def get_schema(self) -> ToolSchema:
        """Get tool schema"""
        return ToolSchema(
            name=self._config.name,
            description=self._config.description,
            parameters=self._config.parameters,
            required=self._config.parameters.get("required", [])
        )

    def get_name(self) -> str:
        """Get tool name"""
        return self._config.name

    def get_description(self) -> str:
        """Get tool description"""
        return self._config.description

    def get_stats(self) -> Dict[str, Any]:
        """Get tool statistics"""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Reset statistics"""
        self._stats = {
            "call_count": 0,
            "success_count": 0,
            "error_count": 0,
            "total_latency": 0.0,
            "avg_latency": 0.0
        }

    def _update_stats(self, success: bool, latency: float) -> None:
        """Update statistics"""
        self._stats["call_count"] += 1
        
        if success:
            self._stats["success_count"] += 1
        else:
            self._stats["error_count"] += 1
        
        self._stats["total_latency"] += latency
        self._stats["avg_latency"] = self._stats["total_latency"] / self._stats["call_count"]


class CalculatorTool(BaseTool):
    """
    Calculator Tool
    
    Executes mathematical calculations.
    """

    def __init__(self):
        config = ToolConfig(
            name="calculator",
            description="Perform mathematical calculations",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression (e.g., 2 + 2, sin(0))"
                    }
                },
                "required": ["expression"]
            }
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute calculation"""
        start_time = time.time()
        
        try:
            expression = params.get("expression", "")
            
            # Safe evaluation
            allowed_names = {
                "abs": abs,
                "max": max,
                "min": min,
                "pow": pow,
                "round": round,
                "sqrt": lambda x: x ** 0.5,
                "sin": lambda x: __import__('math').sin(x),
                "cos": lambda x: __import__('math').cos(x),
                "tan": lambda x: __import__('math').tan(x),
                "log": lambda x: __import__('math').log(x),
                "log10": lambda x: __import__('math').log10(x),
                "pi": __import__('math').pi,
                "e": __import__('math').e,
            }
            
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            
            latency = time.time() - start_time
            self._update_stats(True, latency)
            
            return ToolResult(
                success=True,
                output=str(result),
                latency=latency
            )
            
        except Exception as e:
            latency = time.time() - start_time
            self._update_stats(False, latency)
            
            return ToolResult(
                success=False,
                error=str(e),
                latency=latency
            )


class SearchTool(BaseTool):
    """
    Search Tool
    
    Performs web searches using DuckDuckGo Lite.
    Falls back to mock results if search is unavailable.
    """

    def __init__(self):
        config = ToolConfig(
            name="search",
            description="Search the web for information",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute search using DuckDuckGo Lite"""
        start_time = time.time()
        
        try:
            query = params.get("query", "")
            num_results = params.get("num_results", 5)
            
            if not query:
                latency = time.time() - start_time
                self._update_stats(False, latency)
                return ToolResult(
                    success=False,
                    error="Query parameter is required",
                    latency=latency
                )
            
            results = await self._search_duckduckgo(query, num_results)
            
            latency = time.time() - start_time
            self._update_stats(True, latency)
            
            return ToolResult(
                success=True,
                output=results,
                latency=latency,
                metadata={"query": query, "count": len(results), "source": results[0].get("source", "duckduckgo") if results else "none"}
            )
            
        except Exception as e:
            latency = time.time() - start_time
            self._update_stats(False, latency)
            
            return ToolResult(
                success=False,
                error=str(e),
                latency=latency
            )

    async def _search_duckduckgo(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Search using DuckDuckGo Lite HTML"""
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(
                    "https://lite.duckduckgo.com/lite/",
                    params={"q": query, "kl": "cn-zh"},
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; aiPlatform/1.0)",
                        "Accept": "text/html",
                    }
                )
                
                if response.status_code != 200:
                    return self._mock_results(query, num_results)
                
                from html.parser import HTMLParser
                import urllib.parse
                
                class DDGParser(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.results = []
                        self._current = {}
                        self._in_link = False
                        self._in_snippet = False
                    
                    def handle_starttag(self, tag, attrs):
                        attrs_dict = dict(attrs)
                        if tag == "a" and attrs_dict.get("class") == "result-link":
                            self._in_link = True
                            raw_url = attrs_dict.get("href", "")
                            self._current = {"url": self._clean_url(raw_url), "source": "duckduckgo"}
                        elif tag == "td" and attrs_dict.get("class") == "result-snippet":
                            self._in_snippet = True
                    
                    def handle_endtag(self, tag):
                        if tag == "a" and self._in_link:
                            self._in_link = False
                        elif tag == "td" and self._in_snippet:
                            self._in_snippet = False
                    
                    def handle_data(self, data):
                        data = data.strip()
                        if not data:
                            return
                        if self._in_link and self._current and "title" not in self._current:
                            self._current["title"] = data
                        elif self._in_snippet and self._current and "title" in self._current:
                            self._current["snippet"] = data[:200]
                            self.results.append(self._current)
                            self._current = {}
                            self._in_snippet = False
                    
                    @staticmethod
                    def _clean_url(url: str) -> str:
                        """Extract actual URL from DuckDuckGo redirect"""
                        if url.startswith("//duckduckgo.com/l/"):
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                            return parsed.get("uddg", [url])[0] if "uddg" in parsed else url
                        if url.startswith("//"):
                            return "https:" + url
                        return url
                
                parser = DDGParser()
                parser.feed(response.text)
                
                results = parser.results[:num_results]
                
                if not results:
                    return self._mock_results(query, num_results)
                
                return results
                
        except Exception:
            return self._mock_results(query, num_results)

    def _mock_results(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Fallback mock results"""
        return [
            {
                "title": f"Result {i+1} for {query}",
                "url": f"https://example.com/{i}",
                "snippet": f"This is a mock result for query: {query}",
                "source": "mock"
            }
            for i in range(num_results)
        ]


class FileOperationsTool(BaseTool):
    """
    File Operations Tool
    
    Performs file system operations.
    """

    def __init__(self):
        config = ToolConfig(
            name="file_operations",
            description="Read, write, or list files",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "Operation: read, write, list, delete",
                        "enum": ["read", "write", "list", "delete"]
                    },
                    "path": {
                        "type": "string",
                        "description": "File path"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content for write operation"
                    }
                },
                "required": ["operation", "path"]
            }
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute file operation"""
        start_time = time.time()
        
        try:
            operation = params.get("operation")
            path = params.get("path")
            content = params.get("content", "")
            
            # Placeholder - in production would use actual file system
            result = f"Operation {operation} on {path}"
            
            if operation == "list":
                result = ["file1.txt", "file2.txt", "dir1/"]
            elif operation == "read":
                result = f"Content of {path}"
            elif operation == "write":
                result = f"Wrote to {path}"
            elif operation == "delete":
                result = f"Deleted {path}"
            
            latency = time.time() - start_time
            self._update_stats(True, latency)
            
            return ToolResult(
                success=True,
                output=result,
                latency=latency
            )
            
        except Exception as e:
            latency = time.time() - start_time
            self._update_stats(False, latency)
            
            return ToolResult(
                success=False,
                error=str(e),
                latency=latency
            )


class ToolRegistry:
    """
    Tool Registry
    
    Manages tool registration and retrieval.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[str, List[str]] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool"""
        name = tool.get_name()
        self._tools[name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[str]:
        """List tools"""
        return list(self._tools.keys())

    def unregister(self, name: str) -> None:
        """Unregister a tool"""
        if name in self._tools:
            del self._tools[name]

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all tools"""
        return {name: tool.get_stats() for name, tool in self._tools.items()}


# Global registry
_global_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry"""
    return _global_registry


def create_tool(
    tool_type: str,
    **kwargs
) -> BaseTool:
    """
    Factory function to create tool
    
    Args:
        tool_type: Type of tool ("calculator", "search", "file_operations")
        
    Returns:
        BaseTool: Tool instance
    """
    if tool_type == "calculator":
        return CalculatorTool()
    elif tool_type == "search":
        return SearchTool()
    elif tool_type == "file_operations":
        return FileOperationsTool()
    else:
        raise ValueError(f"Unknown tool type: {tool_type}")