from __future__ import annotations

import base64
import os
import shlex
import time
from typing import Dict, Optional

from .base import ExecDriver, ExecResult


class SSHExecDriver(ExecDriver):
    """
    SSH Exec backend (best-effort).

    Config via env:
    - AIPLAT_SSH_HOST (required)
    - AIPLAT_SSH_USER (optional)
    - AIPLAT_SSH_PORT (optional, default 22)
    - AIPLAT_SSH_IDENTITY_FILE (optional, e.g. ~/.ssh/id_rsa)

    Notes:
    - This driver is intentionally conservative and only supports python code execution.
    - If SSH is not configured, health() returns ok=False.
    """

    driver_id = "ssh"

    def capabilities(self) -> Dict[str, object]:
        return {
            "driver_id": self.driver_id,
            "supported_languages": ["python"],
            "isolation": {
                # depends on remote host configuration; we can't assert isolation here
                "network_isolated": None,
                "filesystem_isolated": None,
                "process_isolated": None,
            },
            "limits": {},
            "config": {
                "required": True,
                "env": ["AIPLAT_SSH_HOST", "AIPLAT_SSH_USER", "AIPLAT_SSH_PORT", "AIPLAT_SSH_IDENTITY_FILE"],
            },
            "notes": "Executes python remotely via ssh (BatchMode=yes). Isolation and limits are determined by the remote host.",
        }

    def _build_target(self) -> Optional[str]:
        host = (os.getenv("AIPLAT_SSH_HOST") or "").strip()
        if not host:
            return None
        user = (os.getenv("AIPLAT_SSH_USER") or "").strip()
        return f"{user}@{host}" if user else host

    def _base_ssh_args(self) -> list[str]:
        port = (os.getenv("AIPLAT_SSH_PORT") or "22").strip()
        ident = (os.getenv("AIPLAT_SSH_IDENTITY_FILE") or "").strip()
        args = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=5"]
        if port:
            args += ["-p", str(port)]
        if ident:
            args += ["-i", ident]
        return args

    async def run_code(self, *, language: str, code: str, timeout_s: float) -> ExecResult:
        if str(language or "").lower() not in {"python", "py"}:
            return ExecResult(ok=False, exit_code=1, error="ssh_exec_driver_only_supports_python")

        target = self._build_target()
        if not target:
            return ExecResult(ok=False, exit_code=1, error="ssh_not_configured")

        # Execute python via base64 to avoid shell quoting pitfalls.
        b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
        remote = f"python3 -c {shlex.quote('import base64;exec(base64.b64decode(' + repr(b64) + ').decode())')}"

        import asyncio

        cmd = self._base_ssh_args() + [target, remote]
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                return ExecResult(ok=False, exit_code=124, error="timeout", duration_ms=int((time.time() - start) * 1000))
            out = (stdout_b or b"").decode("utf-8", errors="replace")
            err = (stderr_b or b"").decode("utf-8", errors="replace")
            code_rc = int(proc.returncode or 0)
            return ExecResult(
                ok=(code_rc == 0),
                exit_code=code_rc,
                stdout=out,
                stderr=err,
                duration_ms=int((time.time() - start) * 1000),
                error=None if code_rc == 0 else "non_zero_exit",
                metadata={"target": target, "driver": "ssh"},
            )
        except Exception as e:
            return ExecResult(ok=False, exit_code=1, error=str(e), duration_ms=int((time.time() - start) * 1000))

    async def health(self) -> Dict[str, object]:
        target = self._build_target()
        if not target:
            return {
                "driver_id": self.driver_id,
                "ok": False,
                "error": "ssh_not_configured",
                "capabilities": self.capabilities(),
            }

        import asyncio

        cmd = self._base_ssh_args() + [target, "echo ok"]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                return {
                    "driver_id": self.driver_id,
                    "ok": False,
                    "error": "timeout",
                    "target": target,
                    "capabilities": self.capabilities(),
                }
            ok = (proc.returncode == 0) and (b"ok" in (stdout_b or b""))
            return {
                "driver_id": self.driver_id,
                "ok": bool(ok),
                "target": target,
                "stderr": (stderr_b or b"").decode("utf-8", errors="replace")[:2000],
                "capabilities": self.capabilities(),
            }
        except Exception as e:
            return {
                "driver_id": self.driver_id,
                "ok": False,
                "error": str(e),
                "capabilities": self.capabilities(),
            }
