"""
HTTP Client Tool

Provides HTTP request capabilities for agents.
"""

import asyncio
from typing import Any, Dict, List, Optional

from ...harness.interfaces import ToolConfig, ToolResult
from .base import BaseTool


class HTTPClientTool(BaseTool):
    """HTTP Client Tool - Make REST API calls"""
    
    SUPPORTED_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
    
    DEFAULT_TIMEOUT = 30000  # 30 seconds
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def __init__(
        self,
        whitelist: Optional[List[str]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_response_size: int = MAX_RESPONSE_SIZE
    ):
        self._whitelist = whitelist or []
        self._timeout = timeout / 1000  # Convert to seconds
        self._max_response_size = max_response_size
        
        config = ToolConfig(
            name="http",
            description="Make HTTP requests to external APIs",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to request"
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method",
                        "enum": self.SUPPORTED_METHODS,
                        "default": "GET"
                    },
                    "headers": {
                        "type": "object",
                        "description": "HTTP headers",
                        "default": {}
                    },
                    "body": {
                        "type": "object",
                        "description": "Request body for POST/PUT/PATCH"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Request timeout in milliseconds"
                    }
                },
                "required": ["url"]
            }
        )
        super().__init__(config)
        
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute HTTP request"""
        import aiohttp
        
        url = params.get("url", "")
        method = params.get("method", "GET").upper()
        headers = params.get("headers", {})
        body = params.get("body")
        timeout_ms = params.get("timeout", self._timeout * 1000)
        
        # Validate URL
        if not url:
            return ToolResult(
                success=False,
                error="URL is required"
            )
            
        # Check whitelist
        if self._whitelist:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            allowed = any(
                domain == w or domain.endswith(f".{w}")
                for w in self._whitelist
            )
            if not allowed:
                return ToolResult(
                    success=False,
                    error=f"URL not in whitelist: {domain}"
                )
        
        # Only allow http/https
        if not url.startswith(("http://", "https://")):
            return ToolResult(
                success=False,
                error="Only HTTP/HTTPS URLs are allowed"
            )
        
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body if body else None
                ) as response:
                    # Check response size
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > self._max_response_size:
                        return ToolResult(
                            success=False,
                            error=f"Response too large: {content_length} bytes"
                        )
                    
                    # Read response
                    text = await response.text()
                    
                    # Truncate if needed
                    if len(text) > self._max_response_size:
                        text = text[:self._max_response_size] + "... [truncated]"
                    
                    return ToolResult(
                        success=True,
                        output={
                            "status": response.status,
                            "headers": dict(response.headers),
                            "body": text
                        },
                        metadata={
                            "url": url,
                            "method": method
                        }
                    )
                    
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error=f"Request timed out after {timeout_ms}ms"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )