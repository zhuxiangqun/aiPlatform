"""
Tool Base Module

Provides base Tool class implementing ITool interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable
import asyncio
import time
import threading
from contextlib import asynccontextmanager

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
        self._permission_manager = None
        self._tracer = None
        self._stats_lock = threading.Lock()
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

    # -----------------------------
    # Roadmap-2: availability checks
    # -----------------------------
    def check_available(self) -> tuple[bool, Optional[str]]:
        """
        Best-effort availability check for operational readiness.

        Returns:
          (available, reason_if_unavailable)
        """
        return True, None

    def set_permission_manager(self, permission_manager: Any) -> None:
        """Inject permission manager (optional)."""
        self._permission_manager = permission_manager

    def set_tracer(self, tracer: Any) -> None:
        """Inject tracer (optional)."""
        self._tracer = tracer

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate parameters"""
        # Check required parameters
        required = self._config.parameters.get("required", [])
        
        for param in required:
            if param not in params:
                return False
        
        return True

    async def _call_with_tracking(
        self,
        params: Dict[str, Any],
        handler: Callable[[], Awaitable[ToolResult]],
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """Unified execution wrapper: validate → (optional) permission → timeout/exception → stats."""
        start_time = time.time()

        @asynccontextmanager
        async def _span():
            if self._tracer is None or not hasattr(self._tracer, "start_span"):
                yield None
                return
            try:
                span_obj = self._tracer.start_span(f"tool.{self.get_name()}")
                if hasattr(span_obj, "__aenter__"):
                    async with span_obj as s:
                        yield s
                elif hasattr(span_obj, "__enter__"):
                    with span_obj as s:
                        yield s
                else:
                    yield span_obj
            except Exception:
                yield None

        if not self.validate_params(params):
            latency = time.time() - start_time
            self._update_stats(False, latency)
            return ToolResult(success=False, error="Invalid params", latency=latency)

        # Optional permission check: only enforced when user_id is provided.
        user_id = params.get("user_id") or params.get("_user_id")
        if self._permission_manager is not None and user_id is not None:
            try:
                from .permission import Permission

                if not self._permission_manager.check_permission(user_id, self.get_name(), Permission.EXECUTE):
                    latency = time.time() - start_time
                    self._update_stats(False, latency)
                    return ToolResult(
                        success=False,
                        error=f"User '{user_id}' lacks EXECUTE permission for tool '{self.get_name()}'",
                        latency=latency,
                    )
            except Exception as e:
                latency = time.time() - start_time
                self._update_stats(False, latency)
                return ToolResult(success=False, error=str(e), latency=latency)

        effective_timeout = timeout
        try:
            async with _span():
                if effective_timeout is not None:
                    result = await asyncio.wait_for(handler(), timeout=effective_timeout)
                else:
                    result = await handler()
            latency = time.time() - start_time
            self._update_stats(result.success, latency)
            result.latency = latency
            return result
        except asyncio.TimeoutError:
            latency = time.time() - start_time
            self._update_stats(False, latency)
            return ToolResult(success=False, error="Timeout", latency=latency)
        except Exception as e:
            latency = time.time() - start_time
            self._update_stats(False, latency)
            return ToolResult(success=False, error=str(e), latency=latency)

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

    # -----------------------------
    # Compatibility properties
    # -----------------------------
    # NOTE: Harness loops historically expect `tool.name` / `tool.description`.
    # Expose these as read-only properties so ToolRegistry tools are usable
    # without additional wrapper objects.
    @property
    def name(self) -> str:
        return self.get_name()

    @property
    def description(self) -> str:
        return self.get_description()

    def __repr__(self) -> str:
        try:
            return f"<Tool {self.get_name()}>"
        except Exception:
            return super().__repr__()

    def get_stats(self) -> Dict[str, Any]:
        """Get tool statistics"""
        with self._stats_lock:
            return self._stats.copy()

    def reset_stats(self) -> None:
        """Reset statistics"""
        with self._stats_lock:
            self._stats = {
                "call_count": 0,
                "success_count": 0,
                "error_count": 0,
                "total_latency": 0.0,
                "avg_latency": 0.0
            }

    def _update_stats(self, success: bool, latency: float) -> None:
        """Update statistics"""
        with self._stats_lock:
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
        """Execute calculation (wrapped)."""

        async def handler() -> ToolResult:
            expression = params.get("expression", "")

            allowed_names = {
                "abs": abs,
                "max": max,
                "min": min,
                "pow": pow,
                "round": round,
                "sqrt": lambda x: x ** 0.5,
                "sin": lambda x: __import__("math").sin(x),
                "cos": lambda x: __import__("math").cos(x),
                "tan": lambda x: __import__("math").tan(x),
                "log": lambda x: __import__("math").log(x),
                "log10": lambda x: __import__("math").log10(x),
                "pi": __import__("math").pi,
                "e": __import__("math").e,
            }

            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return ToolResult(success=True, output=str(result))

        return await self._call_with_tracking(params, handler, timeout=10)


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
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "For list operation: whether to walk recursively",
                        "default": False
                    },
                    "max_entries": {
                        "type": "integer",
                        "description": "For list operation: max number of returned entries",
                        "default": 2000
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "For read/write: max bytes allowed",
                        "default": 200000
                    },
                    "expected_mtime": {
                        "type": "number",
                        "description": "For write/delete: optional optimistic concurrency control; refuse if current mtime differs"
                    }
                },
                "required": ["operation", "path"]
            },
            metadata={
                "risk_level": "sensitive",
                "risk_weight": 30,
            },
        )
        super().__init__(config)
        # Dedup cache for reads: {(path, mtime, max_bytes): content}
        self._read_cache: Dict[str, str] = {}
        self._read_cache_order: list[str] = []
        self._read_cache_max = 64

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute file operation"""
        start_time = time.time()

        try:
            import os
            import stat
            from pathlib import Path
            import hashlib

            operation = (params.get("operation") or "").strip().lower()
            raw_path = str(params.get("path") or "").strip()
            content = str(params.get("content") or "")
            recursive = bool(params.get("recursive", False))
            max_entries = int(params.get("max_entries", 2000) or 2000)
            max_bytes = int(params.get("max_bytes", 200000) or 200000)  # 200KB
            expected_mtime = params.get("expected_mtime", None)

            if not raw_path:
                raise ValueError("path is required")

            # ---- Allowlist roots (required for safety) ----
            roots_raw = os.environ.get("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", "").strip()
            if not roots_raw:
                raise PermissionError("file_operations is disabled: AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS is empty")

            roots: list[str] = []
            for chunk in roots_raw.split(os.pathsep):
                for p in chunk.split(","):
                    if p.strip():
                        roots.append(p.strip())

            # Resolve and enforce within allowed roots
            target = Path(raw_path).expanduser()
            if not target.is_absolute():
                raise PermissionError("path must be absolute")
            try:
                target_resolved = Path(os.path.realpath(str(target)))
            except Exception:
                target_resolved = target

            allowed = False
            for r in roots:
                rp = Path(os.path.realpath(str(Path(r).expanduser())))
                # allow exact root or subpath
                if str(target_resolved) == str(rp) or str(target_resolved).startswith(str(rp) + os.sep):
                    allowed = True
                    break
            if not allowed:
                raise PermissionError("path is not under allowed roots")

            # ---- Extra denylist safety (even inside allowed roots) ----
            deny_segments_raw = os.environ.get(
                "AIPLAT_FILE_OPERATIONS_DENYLIST_SEGMENTS",
                ".ssh,.git,.env,.venv,node_modules,__pycache__,id_rsa,id_ed25519,secrets",
            )
            deny_segments = {s.strip() for s in deny_segments_raw.split(",") if s.strip()}
            parts = {p for p in target_resolved.parts if p}
            if deny_segments and (parts & deny_segments):
                raise PermissionError("path contains denied segment")

            # Disallow special files (devices, sockets, fifos). Symlinks are resolved by realpath above.
            def _ensure_regular_file(p: Path) -> None:
                try:
                    st = p.stat()
                except Exception:
                    return
                if not stat.S_ISREG(st.st_mode):
                    raise PermissionError("refuse to operate on non-regular file")

            def _looks_binary(p: Path) -> bool:
                try:
                    with p.open("rb") as f:
                        chunk = f.read(4096)
                    if b"\x00" in chunk:
                        return True
                    # Heuristic: many non-text bytes
                    if not chunk:
                        return False
                    bad = sum(1 for b in chunk if b < 9 or (b > 13 and b < 32))
                    return (bad / max(len(chunk), 1)) > 0.2
                except Exception:
                    return False

            def _list_dir(p: Path) -> list[str]:
                out: list[str] = []
                if not p.exists():
                    return out
                if not p.is_dir():
                    return [str(p)]
                if recursive:
                    for root, dirs, files in os.walk(str(p)):
                        # best-effort: skip very large walks
                        for d in dirs:
                            out.append(os.path.join(root, d) + os.sep)
                            if len(out) >= max_entries:
                                return out
                        for f in files:
                            out.append(os.path.join(root, f))
                            if len(out) >= max_entries:
                                return out
                else:
                    for x in sorted(p.iterdir(), key=lambda t: t.name):
                        out.append(str(x) + (os.sep if x.is_dir() else ""))
                        if len(out) >= max_entries:
                            break
                return out

            if operation == "list":
                result = _list_dir(target_resolved)
            elif operation == "read":
                if target_resolved.is_dir():
                    raise ValueError("path is a directory; use operation=list")
                if not target_resolved.exists():
                    raise FileNotFoundError("file not found")
                _ensure_regular_file(target_resolved)
                # limit file size
                size = target_resolved.stat().st_size
                if size > max_bytes:
                    raise ValueError(f"file too large (> {max_bytes} bytes)")
                # binary detection
                if _looks_binary(target_resolved) and os.environ.get("AIPLAT_FILE_OPERATIONS_ALLOW_BINARY_READ", "false").lower() not in {
                    "1",
                    "true",
                    "yes",
                    "y",
                }:
                    raise PermissionError("refuse to read binary file (set AIPLAT_FILE_OPERATIONS_ALLOW_BINARY_READ=true to override)")

                mtime = target_resolved.stat().st_mtime
                cache_key = f"{str(target_resolved)}|{mtime}|{max_bytes}"
                cache_hit = cache_key in self._read_cache
                if cache_hit:
                    result = self._read_cache[cache_key]
                else:
                    result = target_resolved.read_text(encoding="utf-8", errors="replace")
                    # cache (best-effort)
                    try:
                        self._read_cache[cache_key] = result
                        self._read_cache_order.append(cache_key)
                        if len(self._read_cache_order) > self._read_cache_max:
                            old = self._read_cache_order.pop(0)
                            self._read_cache.pop(old, None)
                    except Exception:
                        pass
            elif operation == "write":
                if os.environ.get("AIPLAT_FILE_OPERATIONS_ALLOW_WRITE", "false").lower() not in {"1", "true", "yes", "y"}:
                    raise PermissionError("write is disabled by policy (set AIPLAT_FILE_OPERATIONS_ALLOW_WRITE=true)")
                if target_resolved.is_dir():
                    raise ValueError("cannot write to a directory path")
                # ensure parent exists
                target_resolved.parent.mkdir(parents=True, exist_ok=True)
                # optimistic concurrency check (best-effort)
                if expected_mtime is not None and target_resolved.exists():
                    try:
                        cur_mtime = float(target_resolved.stat().st_mtime)
                        if abs(cur_mtime - float(expected_mtime)) > 1e-6:
                            raise PermissionError("mtime mismatch (file changed since last read)")
                    except Exception:
                        raise
                if len(content.encode("utf-8", errors="ignore")) > max_bytes:
                    raise ValueError(f"content too large (> {max_bytes} bytes)")
                target_resolved.write_text(content, encoding="utf-8")
                result = "ok"
            elif operation == "delete":
                if os.environ.get("AIPLAT_FILE_OPERATIONS_ALLOW_DELETE", "false").lower() not in {"1", "true", "yes", "y"}:
                    raise PermissionError("delete is disabled by policy (set AIPLAT_FILE_OPERATIONS_ALLOW_DELETE=true)")
                if target_resolved.is_dir():
                    raise ValueError("refuse to delete directories")
                if expected_mtime is not None and target_resolved.exists():
                    try:
                        cur_mtime = float(target_resolved.stat().st_mtime)
                        if abs(cur_mtime - float(expected_mtime)) > 1e-6:
                            raise PermissionError("mtime mismatch (file changed since last read)")
                    except Exception:
                        raise
                if target_resolved.exists():
                    _ensure_regular_file(target_resolved)
                    target_resolved.unlink()
                result = "ok"
            else:
                raise ValueError("Invalid operation (read|write|list|delete)")

            latency = time.time() - start_time
            self._update_stats(True, latency)
            # best-effort metadata
            md: Dict[str, Any] = {"operation": operation, "path": str(target_resolved)}
            try:
                if operation in {"read", "write"} and target_resolved.exists() and target_resolved.is_file():
                    st = target_resolved.stat()
                    md["size"] = int(st.st_size)
                    md["mtime"] = float(st.st_mtime)
                if operation == "read" and isinstance(result, str):
                    md["sha256"] = hashlib.sha256(result.encode("utf-8", errors="ignore")).hexdigest()
                    md["cache_hit"] = bool(locals().get("cache_hit", False))
            except Exception:
                pass
            return ToolResult(success=True, output=result, latency=latency, metadata=md)
        except Exception as e:
            latency = time.time() - start_time
            self._update_stats(False, latency)
            return ToolResult(success=False, error=str(e), latency=latency)


class ToolRegistry:
    """
    Tool Registry
    
    Manages tool registration and retrieval.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[str, List[str]] = {}
        self._permission_manager: Any = None
        self._tracer: Any = None
        self._lock = threading.RLock()

    def set_permission_manager(self, permission_manager: Any) -> None:
        """Set permission manager and inject into all registered tools."""
        with self._lock:
            self._permission_manager = permission_manager
            for tool in self._tools.values():
                if hasattr(tool, "set_permission_manager"):
                    tool.set_permission_manager(permission_manager)

    def set_tracer(self, tracer: Any) -> None:
        """Set tracer and inject into all registered tools."""
        with self._lock:
            self._tracer = tracer
            for tool in self._tools.values():
                if hasattr(tool, "set_tracer"):
                    tool.set_tracer(tracer)

    def register(self, tool: BaseTool) -> None:
        """Register a tool"""
        with self._lock:
            name = tool.get_name()
            if self._permission_manager is not None and hasattr(tool, "set_permission_manager"):
                tool.set_permission_manager(self._permission_manager)
            if self._tracer is not None and hasattr(tool, "set_tracer"):
                tool.set_tracer(self._tracer)
            self._tools[name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        with self._lock:
            return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[str]:
        """List tools"""
        with self._lock:
            return list(self._tools.keys())

    def get_availability(self, name: str) -> Dict[str, Any]:
        """Return availability info (best-effort)."""
        tool = self.get(name)
        if not tool:
            return {"available": False, "reason": "not_found"}
        try:
            if hasattr(tool, "check_available"):
                ok, reason = tool.check_available()  # type: ignore[misc]
                return {"available": bool(ok), "reason": reason}
        except Exception as e:
            return {"available": False, "reason": str(e)}
        return {"available": True, "reason": None}

    def unregister(self, name: str) -> None:
        """Unregister a tool"""
        with self._lock:
            if name in self._tools:
                del self._tools[name]

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all tools"""
        with self._lock:
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
