"""
Sandbox — process-level execution isolation for pipeline stages.

Executes agent stages in a subprocess to prevent cross-contamination:
- Isolated memory space
- Resource limits (CPU time, memory, process count)
- Configurable timeout
- Stdout/stderr capture
- Exit code handling with signal detection
- Docker backend for container-level isolation

Use via PipelineStageConfig.sandbox=True on any stage.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


_SIGNAL_NAMES: Dict[int, str] = {
    signal.SIGXCPU: "CPU time limit exceeded",
    signal.SIGKILL: "process killed (likely memory limit)",
    signal.SIGTERM: "terminated",
    signal.SIGSEGV: "segmentation fault",
    signal.SIGABRT: "aborted",
}


@dataclass
class SandboxResult:
    success: bool
    output: str
    stderr: str = ""
    exit_code: int = -1
    elapsed_seconds: float = 0.0
    error: str = ""


# disposition: Phase 6 infrastructure — sandbox execution, wiring pending
class StageSandbox:
    """Process-level sandbox with resource limits.

    Resource limits are applied in the subprocess via setrlimit()
    before executing stage logic. The parent detects violations
    by inspecting the subprocess exit code (negative = killed by signal).
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 600,
        cpu_limit_seconds: int = 300,
        memory_limit_mb: int = 1024,
        max_processes: int = 100,
        env: Optional[Dict[str, str]] = None,
    ):
        self._timeout = timeout_seconds
        self._cpu_limit = cpu_limit_seconds
        self._memory_limit_mb = memory_limit_mb
        self._max_processes = max_processes
        self._env = dict(os.environ)
        if env:
            self._env.update(env)
        # Credential isolation: strip LLM API keys from sandbox env.
        # Ensures model-generated code inside sandbox can never access credentials,
        # regardless of how clever prompt injection becomes.
        for k in list(self._env.keys()):
            if k.startswith("AIPLAT_LLM_") or k.startswith("OPENAI_") or k.startswith("ANTHROPIC_"):
                del self._env[k]

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

        # Pass resource limit configs to worker via env
        self._env["AIPLAT_SANDBOX_CPU_LIMIT"] = str(self._cpu_limit)
        self._env["AIPLAT_SANDBOX_MEMORY_MB"] = str(self._memory_limit_mb)
        self._env["AIPLAT_SANDBOX_MAX_PROCS"] = str(self._max_processes)

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
                    exit_code=-1,
                    elapsed_seconds=elapsed,
                    error=f"Stage timed out after {self._timeout}s",
                )

            elapsed = time.time() - start
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            rc = proc.returncode
            if rc == 0:
                return SandboxResult(
                    success=True, output=output, stderr=stderr_str,
                    exit_code=0, elapsed_seconds=elapsed,
                )
            elif rc < 0:
                signum = -rc
                reason = _SIGNAL_NAMES.get(signum, f"signal {signum}")
                return SandboxResult(
                    success=False, output=output, stderr=stderr_str,
                    exit_code=rc, elapsed_seconds=elapsed,
                    error=f"Stage killed: {reason}",
                )
            else:
                return SandboxResult(
                    success=False, output=output, stderr=stderr_str,
                    exit_code=rc, elapsed_seconds=elapsed,
                    error=f"Stage exited with code {rc}",
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
Applies resource limits (CPU/memory/process count) before executing.
"""
import json
import os
import signal
import sys

def _apply_limits():
    """Apply resource limits from env vars before any stage logic runs."""
    try:
        import resource
        cpu = int(os.environ.get("AIPLAT_SANDBOX_CPU_LIMIT", "300"))
        mem_mb = int(os.environ.get("AIPLAT_SANDBOX_MEMORY_MB", "1024"))
        max_procs = int(os.environ.get("AIPLAT_SANDBOX_MAX_PROCS", "100"))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb << 20, mem_mb << 20))
        resource.setrlimit(resource.RLIMIT_NPROC, (max_procs, max_procs))
        # Install SIGXCPU handler for graceful cleanup before hard kill
        signal.signal(signal.SIGXCPU, lambda signum, frame: (
            print(json.dumps({"success": False, "error": "CPU limit exceeded"}), flush=True)
            or sys.exit(1)
        ))
    except Exception:
        pass  # setrlimit not available everywhere (e.g. some macOS versions)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No input file"}))
        sys.exit(1)

    _apply_limits()

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


# disposition: Phase 6 infrastructure — Docker sandbox execution, wiring pending
class DockerSandbox(StageSandbox):
    """Container-level sandbox using Docker for stronger isolation.

    Adds: --memory, --cpus, --read-only, --cap-drop=ALL, --pids-limit.
    Falls back to StageSandbox if Docker is not available.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 600,
        cpu_limit_seconds: int = 300,
        memory_limit_mb: int = 1024,
        max_processes: int = 100,
        image: str = "",
        network_enabled: bool = False,
        env: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            timeout_seconds=timeout_seconds,
            cpu_limit_seconds=cpu_limit_seconds,
            memory_limit_mb=memory_limit_mb,
            max_processes=max_processes,
            env=env,
        )
        self._image = image or os.getenv("AIPLAT_SANDBOX_DOCKER_IMAGE", "python:3.12-slim")
        self._network_enabled = network_enabled

    async def execute(
        self,
        stage_config: dict,
        state_snapshot: dict,
        *,
        project_dir: str = "",
    ) -> SandboxResult:
        import shutil
        if not shutil.which("docker"):
            return await super().execute(stage_config, state_snapshot, project_dir=project_dir)

        import time
        start = time.time()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="aiplat_docker_sandbox_"
        ) as tf:
            json.dump({"stage": stage_config, "state": state_snapshot}, tf)
            input_file = tf.name

        script = os.path.join(os.path.dirname(__file__), "_sandbox_worker.py")
        worker_script = script if os.path.isfile(script) else super()._write_worker()

        host_script_dir = os.path.dirname(worker_script)
        work_dir = project_dir or os.getcwd()

        docker_args = [
            "docker", "run", "--rm",
            "--memory", f"{self._memory_limit_mb}m",
            "--cpus", str(min(self._cpu_limit / 60.0, 1.0)) if self._cpu_limit > 0 else "1.0",
            "--pids-limit", str(self._max_processes),
            "--read-only",
            "--cap-drop", "ALL",
            "--tmpfs", "/tmp:exec,size=256m",
            "-v", f"{host_script_dir}:{host_script_dir}:ro",
            "-v", f"{work_dir}:{work_dir}:rw",
            "-v", f"{input_file}:{input_file}:ro",
            "-w", work_dir,
            "-e", f"AIPLAT_SANDBOX_CPU_LIMIT={self._cpu_limit}",
            "-e", f"AIPLAT_SANDBOX_MEMORY_MB={self._memory_limit_mb}",
            "-e", f"AIPLAT_SANDBOX_MAX_PROCS={self._max_processes}",
        ]
        if not self._network_enabled:
            docker_args += ["--network", "none"]
        docker_args += [self._image, sys.executable, worker_script, input_file]

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout + 30  # Docker overhead
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                elapsed = time.time() - start
                return SandboxResult(success=False, exit_code=-1, elapsed_seconds=elapsed,
                                     error=f"Stage timed out after {self._timeout}s", output="")

            elapsed = time.time() - start
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            rc = proc.returncode
            if rc == 0:
                return SandboxResult(success=True, output=output, stderr=stderr_str,
                                     exit_code=0, elapsed_seconds=elapsed)
            elif rc < 0:
                signum = -rc
                reason = _SIGNAL_NAMES.get(signum, f"signal {signum}")
                return SandboxResult(success=False, output=output, stderr=stderr_str,
                                     exit_code=rc, elapsed_seconds=elapsed,
                                     error=f"Stage killed: {reason}")
            elif rc == 125 or rc == 126:
                return SandboxResult(success=False, output=output, stderr=stderr_str,
                                     exit_code=rc, elapsed_seconds=elapsed,
                                     error=f"Docker error (code {rc}): check image and permissions")
            else:
                return SandboxResult(success=False, output=output, stderr=stderr_str,
                                     exit_code=rc, elapsed_seconds=elapsed,
                                     error=f"Stage exited with code {rc}")
        finally:
            try:
                os.unlink(input_file)
            except OSError:
                pass


def create_sandbox(stage_config: Any, **kwargs) -> StageSandbox:
    """Create the appropriate sandbox based on stage config.

    stage.sandbox_mode="docker" → DockerSandbox (falls back to StageSandbox if Docker missing)
    default → StageSandbox (subprocess with resource limits)
    """
    mode = getattr(stage_config, "sandbox_mode", "subprocess") or "subprocess"
    if mode == "docker":
        return DockerSandbox(**kwargs)
    return StageSandbox(**kwargs)


__all__ = [
    "StageSandbox",
    "DockerSandbox",
    "SandboxResult",
    "create_sandbox",
]
