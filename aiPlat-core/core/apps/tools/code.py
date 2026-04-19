"""
Code Execution Tool

Provides safe code execution capabilities for agents.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ...harness.interfaces import ToolConfig, ToolResult
from ..exec_drivers.registry import get_exec_backend, get_exec_driver
from .base import BaseTool


class CodeExecutionTool(BaseTool):
    """Code Execution Tool - Safe sandboxed code execution"""
    
    SUPPORTED_LANGUAGES = ["python", "javascript"]
    
    DEFAULT_TIMEOUT = 30000  # 30 seconds
    MAX_CPU_PERCENT = 50
    MAX_MEMORY_MB = 512
    
    def __init__(
        self,
        allowed_languages: Optional[list] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_cpu_percent: int = MAX_CPU_PERCENT,
        max_memory_mb: int = MAX_MEMORY_MB,
        network_isolation: bool = True
    ):
        self._allowed_languages = allowed_languages or self.SUPPORTED_LANGUAGES
        self._timeout = timeout / 1000
        self._max_cpu_percent = max_cpu_percent
        self._max_memory_mb = max_memory_mb
        self._network_isolation = network_isolation
        
        config = ToolConfig(
            name="code",
            description="Execute code in a sandboxed environment",
            parameters={
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "description": "Programming language",
                        "enum": self._allowed_languages
                    },
                    "code": {
                        "type": "string",
                        "description": "Code to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Execution timeout in milliseconds"
                    }
                },
                "required": ["language", "code"]
            },
            metadata={
                # Used by Kernel approval/priority system
                "risk_level": "dangerous",
                "risk_weight": 40,
            },
        )
        super().__init__(config)
        
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute code in sandbox"""
        language = params.get("language", "python")
        code = params.get("code", "")
        timeout_ms = params.get("timeout", self._timeout * 1000)
        
        if not code:
            return ToolResult(
                success=False,
                error="Code is required"
            )
        
        if language not in self._allowed_languages:
            return ToolResult(
                success=False,
                error=f"Language not allowed: {language}"
            )
        
        backend = "local"
        try:
            backend = await get_exec_backend()
        except Exception:
            backend = "local"
        driver = get_exec_driver(backend)

        res = await driver.run_code(language=str(language), code=str(code), timeout_s=float(timeout_ms) / 1000.0)
        return ToolResult(
            success=bool(res.ok),
            output={
                "backend": backend,
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "duration_ms": res.duration_ms,
                "metadata": res.metadata,
            },
            error=res.error,
            metadata={"backend": backend},
        )
        
    async def _execute_python(self, code: str, timeout: float) -> ToolResult:
        """Execute Python code"""
        return ToolResult(success=False, error="deprecated: use ExecDriver")
        
    async def _execute_javascript(self, code: str, timeout: float) -> ToolResult:
        """Execute JavaScript code"""
        return ToolResult(success=False, error="deprecated: use ExecDriver")
