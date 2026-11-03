"""B3-L.3 — constrained docker exec for allowlisted cli_probe commands.

Honesty:
- Uses ``docker run --network=none`` (+ read-only / memory / pids).
- Not a microVM; ``sandbox_real_isolation`` stays false at policy layer.
- Command argv must match allowlist; no shell string execution.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Dict, List, Sequence, Tuple

# Only exact first-token matches (no shell metacharacters).
CLI_ALLOWLIST: frozenset[str] = frozenset(
    {
        "true",
        "false",
        "echo",
        "uname",
        "id",
        "pwd",
        "ls",
        "cat",
        "wc",
        "head",
        "tail",
    }
)


def docker_bin() -> str:
    return (os.environ.get("AIPLAT_EVAL_DOCKER_BIN") or "docker").strip() or "docker"


def docker_available() -> bool:
    path = docker_bin()
    if path != "docker" and os.path.isfile(path) and os.access(path, os.X_OK):
        return True
    return shutil.which(path) is not None


def docker_image() -> str:
    return (os.environ.get("AIPLAT_EVAL_SANDBOX_IMAGE") or "alpine:3.20").strip()


def validate_cli_argv(argv: Sequence[str]) -> Tuple[bool, str]:
    if not argv:
        return False, "empty_argv"
    cmd = str(argv[0] or "").strip()
    if not cmd or cmd not in CLI_ALLOWLIST:
        return False, f"command_not_allowlisted:{cmd or '<empty>'}"
    for part in argv:
        s = str(part)
        if any(ch in s for ch in (";", "|", "&", "`", "$", "\n", "\r")):
            return False, "metachar_forbidden"
        if s.startswith("-") and cmd in ("cat", "ls", "head", "tail", "wc"):
            # Disallow path escape flags; keep simple.
            if s in ("-r", "-R", "--recursive"):
                return False, "flag_forbidden"
    return True, ""


def run_in_docker(
    argv: Sequence[str],
    *,
    timeout_s: float | None = None,
) -> Dict[str, Any]:
    """Run argv inside a disposable container. Returns ok/stdout/stderr/audit."""
    ok_argv, detail = validate_cli_argv(argv)
    if not ok_argv:
        return {
            "ok": False,
            "exit_code": 126,
            "stdout": "",
            "stderr": detail,
            "audit": {
                "backend": "docker",
                "network": "none",
                "image": docker_image(),
                "argv": list(argv),
                "detail": detail,
                "docker_available": docker_available(),
            },
        }
    if not docker_available():
        return {
            "ok": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": "docker_unavailable",
            "audit": {
                "backend": "docker",
                "detail": "docker_unavailable",
                "docker_available": False,
            },
        }

    timeout = float(
        timeout_s
        if timeout_s is not None
        else (os.environ.get("AIPLAT_EVAL_SANDBOX_TIMEOUT") or "15")
    )
    image = docker_image()
    docker = docker_bin()
    cmd: List[str] = [
        docker,
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "--memory=128m",
        "--cpus=0.5",
        "--pids-limit=64",
        "--user",
        "65534:65534",
        image,
        *list(argv),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout),
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": int(proc.returncode),
            "stdout": (proc.stdout or "")[:8000],
            "stderr": (proc.stderr or "")[:4000],
            "audit": {
                "backend": "docker",
                "network": "none",
                "image": image,
                "argv": list(argv),
                "docker_available": True,
                "isolation": "container",
                "microvm": False,
            },
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": "",
            "stderr": "timeout",
            "audit": {
                "backend": "docker",
                "network": "none",
                "image": image,
                "argv": list(argv),
                "detail": "timeout",
                "docker_available": True,
            },
        }
    except OSError as exc:
        return {
            "ok": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": f"os_error:{exc}",
            "audit": {
                "backend": "docker",
                "detail": f"os_error:{type(exc).__name__}",
                "docker_available": docker_available(),
            },
        }


def _wire_docker() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    _ = docker_available()
    return run_in_docker(["true"])
