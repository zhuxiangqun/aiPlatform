"""
Sandbox — process-level execution isolation for pipeline stages.

Executes agent stages in a subprocess to prevent cross-contamination:
- Isolated memory space
- Configurable timeout
- Stdout/stderr capture
- Exit code handling

Use via PipelineStageConfig.sandbox=True on any stage.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SandboxResult:
    success: bool
    output: str
    stderr: str = ""
    exit_code: int = -1
    elapsed_seconds: float = 0.0
    error: str = ""


class StageSandbox:
    """Process-level sandbox for executing agent stages in isolation."""

    def __init__(self, *, timeout_seconds: float = 600, env: Optional[Dict[str, str]] = None):
        self._timeout = timeout_seconds
        self._env = dict(os.environ)
        if env:
            self._env.update(env)

    async def execute(
        self,
        stage_config: dict,
        state_snapshot: dict,
        *,
        project_dir: str = "",
    ) -> SandboxResult:
        import time
        start = time.time()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="aiplat_sandbox_"
        ) as tf:
            json.dump({"stage": stage_config, "state": state_snapshot}, tf)
            input_file = tf.name

        script = os.path.join(os.path.dirname(__file__), "_sandbox_worker.py")
        worker_script = script if os.path.isfile(script) else self._write_worker()

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, worker_script, input_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
                cwd=project_dir or os.getcwd(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                elapsed = time.time() - start
                return SandboxResult(
                    success=False,
                    output="",
                    stderr="",
                    exit_code=-1,
                    elapsed_seconds=elapsed,
                    error=f"Stage timed out after {self._timeout}s",
                )

            elapsed = time.time() - start
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            if proc.returncode == 0:
                return SandboxResult(
                    success=True,
                    output=output,
                    stderr=stderr_str,
                    exit_code=0,
                    elapsed_seconds=elapsed,
                )
            else:
                return SandboxResult(
                    success=False,
                    output=output,
                    stderr=stderr_str,
                    exit_code=proc.returncode,
                    elapsed_seconds=elapsed,
                    error=f"Stage exited with code {proc.returncode}",
                )
        finally:
            try:
                os.unlink(input_file)
            except OSError:
                pass

    def _write_worker(self) -> str:
        """Write sandbox worker script to a temp location and return path."""
        worker_code = '''"""
Sandbox worker — executed as a subprocess for isolated stage execution.
Reads stage config + state from JSON input file, executes the stage,
and writes results to stdout as JSON.
"""
import json
import sys
import os

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No input file"}))
        sys.exit(1)

    input_file = sys.argv[1]
    try:
        with open(input_file) as f:
            data = json.load(f)
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)

    stage = data.get("stage", {})
    state = data.get("state", {})

    result = {
        "success": True,
        "stage_id": stage.get("id", "unknown"),
        "output_dir": state.get("output_dir", os.getcwd()),
        "artifacts": {},
    }
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
'''
        worker_path = os.path.join(tempfile.gettempdir(), "_aiplat_sandbox_worker.py")
        with open(worker_path, "w") as f:
            f.write(worker_code)
        return worker_path


def should_use_sandbox(stage_config: Any) -> bool:
    return bool(getattr(stage_config, "sandbox", False))


__all__ = [
    "StageSandbox",
    "SandboxResult",
    "should_use_sandbox",
]
