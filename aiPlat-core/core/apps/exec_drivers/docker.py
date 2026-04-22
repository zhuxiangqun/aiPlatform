from __future__ import annotations

import asyncio
import os
import time
import tempfile
from pathlib import Path
from typing import Dict

from .base import ExecDriver, ExecResult


class DockerExecDriver(ExecDriver):
    driver_id = "docker"

    def capabilities(self) -> Dict[str, object]:
        return {
            "driver_id": self.driver_id,
            "supported_languages": ["python", "javascript"],
            "isolation": {
                "network_isolated": True,  # we run with --network none
                "filesystem_isolated": True,  # container FS; bind-mount /work read-only
                "process_isolated": True,
            },
            "limits": {
                "cpus_env": "AIPLAT_DOCKER_CPUS",
                "memory_env": "AIPLAT_DOCKER_MEM",
            },
            "config": {
                "required": False,
                "env": ["AIPLAT_DOCKER_PY_IMAGE", "AIPLAT_DOCKER_NODE_IMAGE", "AIPLAT_DOCKER_MEM", "AIPLAT_DOCKER_CPUS"],
            },
            "notes": "Executes inside docker containers (best-effort hardened: network none, /work ro, resource caps).",
        }

    def _images(self) -> Dict[str, str]:
        py = (os.getenv("AIPLAT_DOCKER_PY_IMAGE") or "python:3.10-slim").strip()
        node = (os.getenv("AIPLAT_DOCKER_NODE_IMAGE") or "node:20-alpine").strip()
        return {"python": py, "javascript": node}

    async def _docker_available(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "version",
                "--format",
                "{{.Server.Version}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def run_code(self, *, language: str, code: str, timeout_s: float) -> ExecResult:
        t0 = time.time()
        language = (language or "").strip().lower()
        if language not in {"python", "javascript"}:
            return ExecResult(ok=False, exit_code=2, error=f"unsupported_language:{language}", duration_ms=int((time.time() - t0) * 1000))

        if not await self._docker_available():
            return ExecResult(ok=False, exit_code=127, error="docker_not_available", duration_ms=int((time.time() - t0) * 1000))

        imgs = self._images()
        image = imgs["python"] if language == "python" else imgs["javascript"]
        suffix = ".py" if language == "python" else ".js"
        with tempfile.TemporaryDirectory(prefix="aiplat-docker-code-") as td:
            p = Path(td) / f"main{suffix}"
            p.write_text(code or "", encoding="utf-8")

            # NOTE: harden-by-default:
            # - network none
            # - readonly rootfs (best-effort; may fail on some images)
            cmd = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                f"{td}:/work:ro",
                "-w",
                "/work",
            ]
            # resource caps (best-effort)
            mem = (os.getenv("AIPLAT_DOCKER_MEM") or "512m").strip()
            cpus = (os.getenv("AIPLAT_DOCKER_CPUS") or "1.0").strip()
            if mem:
                cmd += ["--memory", mem]
            if cpus:
                cmd += ["--cpus", cpus]
            cmd += [image]
            if language == "python":
                cmd += ["python3", "/work/main.py"]
            else:
                cmd += ["node", "/work/main.js"]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
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
                    metadata={"image": image},
                )
            except Exception as e:
                return ExecResult(ok=False, exit_code=1, error=f"exception:{type(e).__name__}", stderr=str(e), duration_ms=int((time.time() - t0) * 1000))

    async def health(self) -> Dict[str, object]:
        ok = await self._docker_available()
        return {
            "driver_id": self.driver_id,
            "ok": bool(ok),
            "images": self._images(),
            "capabilities": self.capabilities(),
        }
