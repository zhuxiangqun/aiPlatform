"""cli_probe — docker (network=none) or microVM Linux track (host allowlist v1)."""
from __future__ import annotations

from typing import Any, Dict, List

from app.sandbox.docker_exec import run_in_docker
from app.sandbox.microvm_exec import run_allowlisted_cli
from app.sandbox.policy import sandbox_admits, sandbox_backend
from app.worker.runners._common import runner_result


def run_cli_probe(job: Dict[str, Any]) -> Dict[str, Any]:
    rid = "cli_probe"
    job_id = str(job.get("job_id") or "")
    if not sandbox_admits(rid):
        raise ValueError(f"sandbox_required:{rid}")

    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    argv_raw = payload.get("argv") or payload.get("command")
    argv: List[str]
    if isinstance(argv_raw, str):
        argv = argv_raw.split()
    elif isinstance(argv_raw, list):
        argv = [str(x) for x in argv_raw]
    else:
        argv = ["true"]

    backend = sandbox_backend()
    if backend == "microvm":
        result = run_allowlisted_cli(argv)
        mode = "microvm_track_host_allowlist"
    else:
        result = run_in_docker(argv)
        mode = "docker_cli"

    ok = bool(result.get("ok"))
    return runner_result(
        runner_id=rid,
        job_id=job_id,
        ok=ok,
        metrics={
            "exit_code": float(result.get("exit_code") or 0),
            "pass": 1.0 if ok else 0.0,
        },
        evidence={
            "stdout": result.get("stdout") or "",
            "stderr": result.get("stderr") or "",
            "sandbox": result.get("audit") or {},
            "sandbox_backend": backend,
        },
        detail="" if ok else str(
            (result.get("audit") or {}).get("detail") or result.get("stderr") or "cli_failed"
        ),
        mode=mode,
    )
