from __future__ import annotations

import asyncio
import time
import tempfile
from pathlib import Path
from typing import Dict

from .base import ExecDriver, ExecResult


class LocalExecDriver(ExecDriver):
    driver_id = "local"

    async def run_code(self, *, language: str, code: str, timeout_s: float) -> ExecResult:
        t0 = time.time()
        language = (language or "").strip().lower()
        if language not in {"python", "javascript"}:
            return ExecResult(ok=False, exit_code=2, error=f"unsupported_language:{language}", duration_ms=int((time.time() - t0) * 1000))

        suffix = ".py" if language == "python" else ".js"
        with tempfile.TemporaryDirectory(prefix="aiplat-code-") as td:
            p = Path(td) / f"main{suffix}"
            p.write_text(code or "", encoding="utf-8")

            if language == "python":
                cmd = ["python3", str(p)]
            else:
                cmd = ["node", str(p)]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(Path(td)),
                )
                try:
                    stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return ExecResult(ok=False, exit_code=124, error="timeout", duration_ms=int((time.time() - t0) * 1000))
                return ExecResult(
                    ok=proc.returncode == 0,
                    exit_code=int(proc.returncode or 0),
                    stdout=(stdout_b or b"").decode("utf-8", errors="replace"),
                    stderr=(stderr_b or b"").decode("utf-8", errors="replace"),
                    duration_ms=int((time.time() - t0) * 1000),
                )
            except Exception as e:
                return ExecResult(ok=False, exit_code=1, error=f"exception:{type(e).__name__}", stderr=str(e), duration_ms=int((time.time() - t0) * 1000))

    async def health(self) -> Dict[str, object]:
        # best-effort: check interpreters exist
        ok_py = True
        ok_node = True
        try:
            proc = await asyncio.create_subprocess_exec("python3", "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()
            ok_py = proc.returncode == 0
        except Exception:
            ok_py = False
        try:
            proc = await asyncio.create_subprocess_exec("node", "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()
            ok_node = proc.returncode == 0
        except Exception:
            ok_node = False
        return {"driver_id": self.driver_id, "ok": bool(ok_py and ok_node), "python": ok_py, "node": ok_node}

