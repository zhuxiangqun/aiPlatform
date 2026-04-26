"""
Skill scripts governance tools (P1-3).

提供一个受控入口运行 Skill scripts/ 里的脚本：
- 白名单扩展名与解释器
- 超时
- 输出截断
- 证据：脚本 sha256 / mtime / size

注意：这是高风险能力，默认应由权限/审批系统控制（PolicyGate + PermissionManager）。
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.apps.tools.base import BaseTool
from core.harness.interfaces import ToolConfig, ToolResult
from core.apps.skills.registry import get_skill_registry


def _hash_file(path: Path, *, max_bytes: int = 1024 * 1024) -> str:
    import hashlib

    try:
        h = hashlib.sha256()
        size = path.stat().st_size
        with path.open("rb") as f:
            if size <= max_bytes:
                h.update(f.read())
            else:
                h.update(f.read(max_bytes))
                h.update(f"<size:{size}>".encode("utf-8"))
        return h.hexdigest()
    except Exception:
        return ""


class SkillRunScriptTool(BaseTool):
    """
    运行某个 Skill 的 scripts/ 下脚本（受控执行）。

    Params:
      - skill: skill 名
      - script: 脚本文件名（必须在该 skill 的 scripts/ 目录内）
      - args: 字符串数组（会按参数逐个传递，不经过 shell）
      - timeout_seconds: 超时（默认 20s）
      - max_output_chars: stdout/stderr 截断（默认 8000）
    """

    def __init__(self, *, timeout: int = 20000):
        config = ToolConfig(
            name="skill_run_script",
            description="运行某个 Skill 的 scripts/ 脚本（高风险；受权限/审批治理）",
            parameters={
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "技能名（必填）"},
                    "script": {"type": "string", "description": "脚本文件名（必填）"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "脚本参数（可选）"},
                    "timeout_seconds": {"type": "number", "description": "超时秒数（默认 20）"},
                    "max_output_chars": {"type": "integer", "description": "输出最大字符数（默认 8000）"},
                },
                "required": ["skill", "script"],
            },
            metadata={"category": "skills", "risk_level": "high", "risk_weight": 10},
        )
        super().__init__(config)
        self._timeout_ms = int(timeout or 20000)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        async def handler() -> ToolResult:
            reg = get_skill_registry()
            skill = str(params.get("skill") or "").strip()
            script = str(params.get("script") or "").strip()
            if not skill or not script:
                return ToolResult(success=False, error="skill_and_script_required")

            s = reg.get(skill)
            if not s:
                return ToolResult(success=False, error=f"skill_not_found:{skill}")

            cfg = s.get_config()
            meta = dict(getattr(cfg, "metadata", {}) or {})
            fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
            scripts_dir = str(fs.get("scripts_dir") or "")
            if not scripts_dir:
                return ToolResult(success=False, error="scripts_dir_missing")

            base = Path(scripts_dir).resolve()
            target = (base / script).resolve()
            if not str(target).startswith(str(base)):
                return ToolResult(success=False, error="invalid_script_path")
            if not target.exists() or not target.is_file():
                return ToolResult(success=False, error="script_not_found")

            allowed_exts = [x.strip().lower() for x in (os.getenv("AIPLAT_SKILL_SCRIPT_ALLOWED_EXTS", ".py,.sh").split(",")) if x.strip()]
            if target.suffix.lower() not in allowed_exts:
                return ToolResult(success=False, error=f"script_ext_not_allowed:{target.suffix}")

            # Interpreter whitelist
            if target.suffix.lower() == ".py":
                cmd = ["python3", str(target)]
            elif target.suffix.lower() == ".sh":
                cmd = ["bash", str(target)]
            else:
                return ToolResult(success=False, error="unsupported_script_type")

            extra_args = params.get("args") or []
            if isinstance(extra_args, str):
                # allow "a b c" form (best-effort)
                extra_args = shlex.split(extra_args)
            if isinstance(extra_args, list):
                cmd.extend([str(x) for x in extra_args[:50]])

            timeout_s = params.get("timeout_seconds")
            try:
                timeout_s = float(timeout_s) if timeout_s is not None else 20.0
            except Exception:
                timeout_s = 20.0
            timeout_s = max(0.5, min(timeout_s, 120.0))

            max_out = int(params.get("max_output_chars") or 8000)
            max_out = max(200, min(max_out, 200000))

            start = time.time()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(base),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={**os.environ},
                )
                try:
                    out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return ToolResult(success=False, error="script_timeout")

                end = time.time()
                stdout = (out_b or b"").decode("utf-8", errors="replace")
                stderr = (err_b or b"").decode("utf-8", errors="replace")
                truncated = False
                if len(stdout) + len(stderr) > max_out:
                    truncated = True
                    keep = max_out
                    merged = (stdout + "\n--- stderr ---\n" + stderr)[:keep]
                    stdout = merged
                    stderr = ""

                st = target.stat()
                return ToolResult(
                    success=(proc.returncode == 0),
                    output={
                        "cmd": cmd,
                        "returncode": proc.returncode,
                        "stdout": stdout,
                        "stderr": stderr,
                        "truncated": truncated,
                        "duration_ms": (end - start) * 1000.0,
                        "script": {
                            "name": target.name,
                            "sha256": _hash_file(target),
                            "size": int(st.st_size),
                            "mtime": float(st.st_mtime),
                        },
                    },
                    error=None if proc.returncode == 0 else "script_failed",
                )
            except Exception as e:
                return ToolResult(success=False, error=f"script_error:{e}")

        return await self._call_with_tracking(params, handler, timeout=float(self._timeout_ms / 1000.0))

