"""
WebFetch Tool

Provides web content fetching capabilities.
"""

import asyncio
from typing import Any, Dict, Optional

from ...harness.interfaces import ToolConfig, ToolResult
from .base import BaseTool


class WebFetchTool(BaseTool):
    """Web Fetch Tool - Fetch web page content"""
    
    DEFAULT_TIMEOUT = 30000  # 30 seconds
    MAX_CONTENT_SIZE = 1024 * 1024  # 1MB
    
    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_content_size: int = MAX_CONTENT_SIZE,
        user_agent: str = "aiplat-core/1.0"
    ):
        self._timeout = timeout / 1000
        self._max_content_size = max_content_size
        self._user_agent = user_agent
        
        config = ToolConfig(
            name="webfetch",
            description="Fetch web page content",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch"
                    },
                    "extract": {
                        "type": "string",
                        "description": "What to extract: 'text' | 'html' | 'links'"
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
        """Fetch web content"""
        import aiohttp
        
        url = params.get("url", "")
        extract = params.get("extract", "text")
        timeout_ms = params.get("timeout", self._timeout * 1000)
        
        if not url:
            return ToolResult(
                success=False,
                error="URL is required"
            )
        
        # Only allow http/https
        if not url.startswith(("http://", "https://")):
            return ToolResult(
                success=False,
                error="Only HTTP/HTTPS URLs are allowed"
            )
        
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
        headers = {"User-Agent": self._user_agent}
        
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return ToolResult(
                            success=False,
                            error=f"HTTP {response.status}"
                        )
                    
                    content = await response.text()
                    
                    # Limit content size
                    if len(content) > self._max_content_size:
                        content = content[:self._max_content_size] + "... [truncated]"
                    
                    # Extract based on request
                    if extract == "html":
                        output = content
                    elif extract == "links":
                        import re
                        links = re.findall(r'href=["\']([^"\']+)["\']', content)
                        output = "\n".join(links[:50])  # Limit to 50 links
                    else:  # text
                        # Simple text extraction - remove HTML tags
                        import re
                        text = re.sub(r'<[^>]+>', '', content)
                        text = re.sub(r'\s+', ' ', text).strip()
                        output = text[:5000]  # Limit text output
                    
                    return ToolResult(
                        success=True,
                        output=output,
                        metadata={
                            "url": url,
                            "status": response.status,
                            "content_length": len(content)
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