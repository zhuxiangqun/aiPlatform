"""
Script Runner Module

Provides sandboxed script execution for deterministic skill operations.
"""

import asyncio
import time
import os
from pathlib import Path
from typing import Dict, List, Optional

from .types import SandboxConfig, ScriptResult


class ScriptPermissionChecker:
    """脚本权限检查器"""
    
    def __init__(self, config: SandboxConfig):
        self._config = config
    
    def check(self, script_path: str) -> Optional[str]:
        """检查脚本是否安全，返回错误信息或 None"""
        path = Path(script_path)
        
        if not path.exists():
            return f"Script not found: {script_path}"
        
        ext = path.suffix.lower()
        if ext not in self._config.allowed_extensions:
            return f"Disallowed extension: {ext}"
        
        parent = path.parent
        if ".." in str(path.relative_to(parent)):
            return "Path traversal detected"
        
        try:
            content = path.read_text()
            for blocked in self._config.blocked_commands:
                if blocked in content:
                    return f"Blocked command detected: {blocked}"
        except Exception as e:
            return f"Cannot read script: {e}"
        
        return None


class ScriptRunner:
    """确定性脚本执行器"""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self._config = config or SandboxConfig.get_default()
        self._checker = ScriptPermissionChecker(self._config)
    
    def _get_interpreter(self, script_path: str) -> Optional[List[str]]:
        """获取脚本解释器"""
        ext = Path(script_path).suffix.lower()
        
        interpreter_map = {
            ".sh": ["bash"],
            ".py": ["python3"],
            ".js": ["node"],
        }
        
        return interpreter_map.get(ext)
    
    async def execute(
        self,
        script_path: str,
        args: List[str] = None,
        env: Dict[str, str] = None,
        cwd: str = None
    ) -> ScriptResult:
        """执行脚本"""
        start_time = time.time()
        
        error = self._checker.check(script_path)
        if error:
            return ScriptResult(
                success=False,
                error=error,
                execution_time=time.time() - start_time
            )
        
        interpreter = self._get_interpreter(script_path)
        if not interpreter:
            return ScriptResult(
                success=False,
                error=f"Unsupported script type: {script_path}",
                execution_time=time.time() - start_time
            )
        
        cmd = interpreter + [script_path]
        if args:
            cmd.extend(args)
        
        safe_env = os.environ.copy()
        if env:
            for key, value in env.items():
                if key in self._config.allowed_env_vars:
                    safe_env[key] = value
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=safe_env,
                cwd=cwd,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._config.max_execution_time
                )
                
                execution_time = time.time() - start_time
                
                return ScriptResult(
                    success=process.returncode == 0,
                    stdout=stdout.decode('utf-8', errors='replace'),
                    stderr=stderr.decode('utf-8', errors='replace'),
                    exit_code=process.returncode,
                    execution_time=execution_time
                )
                
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ScriptResult(
                    success=False,
                    error=f"Execution timeout ({self._config.max_execution_time}s)",
                    execution_time=self._config.max_execution_time
                )
                
        except Exception as e:
            return ScriptResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    async def execute_inline(
        self,
        script_content: str,
        script_type: str,
        args: List[str] = None
    ) -> ScriptResult:
        """执行内联脚本内容"""
        import tempfile
        
        type_map = {
            "python": ".py",
            "shell": ".sh",
            "javascript": ".js",
        }
        
        ext = type_map.get(script_type, ".sh")
        
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix=ext,
            delete=False
        ) as f:
            f.write(script_content)
            temp_path = f.name
        
        try:
            return await self.execute(temp_path, args)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def get_script_runner(config: Optional[SandboxConfig] = None) -> ScriptRunner:
    """获取默认脚本执行器"""
    return ScriptRunner(config)


__all__ = [
    "ScriptRunner",
    "ScriptPermissionChecker",
    "get_script_runner",
]