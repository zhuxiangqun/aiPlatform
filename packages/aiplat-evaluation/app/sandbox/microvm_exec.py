"""microVM track exec helpers — version probe + allowlisted host CLI.

Honesty:
- Allowlisted CLI runs on the **host** under microVM **policy** when
  ``microvm_can_admit_runners()``; audit records ``backend=microvm_track``.
- Guest Firecracker boot is separate (``app.sandbox.guest_boot.probe_guest_boot``);
  CLI audit ``guest_boot`` mirrors the process cache (InstanceStart success).
- Not a certification of isolation (``sandbox_real_isolation`` stays false).
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Sequence

from app.sandbox.docker_exec import CLI_ALLOWLIST, validate_cli_argv
from app.sandbox.microvm import (
    guest_boot_cached,
    microvm_bin,
    microvm_can_admit_runners,
    microvm_status,
)


def probe_runtime(timeout_s: float = 5.0) -> Dict[str, Any]:
    """Run ``<bin> --version`` (or ``-V``) when binary exists."""
    bin_path = microvm_bin()
    st = microvm_status()
    if not st.get("microvm_available"):
        return {
            "ok": False,
            "stdout": "",
            "stderr": "microvm_bin_missing",
            "audit": {"backend": "microvm_track", "probe": "version", **{k: st[k] for k in (
                "microvm_ready", "microvm_host_ok", "kvm_available", "guest_boot"
            )}},
        }
    for args in ([bin_path, "--version"], [bin_path, "-V"], [bin_path, "--help"]):
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except OSError as exc:
            return {
                "ok": False,
                "stdout": "",
                "stderr": str(exc),
                "audit": {"backend": "microvm_track", "probe": "version", "args": args},
            }
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 or "firecracker" in out.lower() or "version" in out.lower():
            return {
                "ok": True,
                "stdout": (proc.stdout or "")[:2000],
                "stderr": (proc.stderr or "")[:500],
                "exit_code": proc.returncode,
                "audit": {
                    "backend": "microvm_track",
                    "probe": "version",
                    "args": args,
                    "guest_boot": guest_boot_cached(),
                    "kvm_available": st.get("kvm_available"),
                    "microvm_host_ok": st.get("microvm_host_ok"),
                },
            }
    return {
        "ok": False,
        "stdout": "",
        "stderr": "version_probe_failed",
        "audit": {
            "backend": "microvm_track",
            "probe": "version",
            "guest_boot": guest_boot_cached(),
        },
    }


def run_allowlisted_cli(
    argv: Sequence[str],
    *,
    timeout_s: float | None = None,
) -> Dict[str, Any]:
    """Allowlisted argv under microVM track policy (host process)."""
    boot = guest_boot_cached()
    if not microvm_can_admit_runners():
        return {
            "ok": False,
            "exit_code": 126,
            "stdout": "",
            "stderr": "microvm_admit_denied",
            "audit": {
                "backend": "microvm_track",
                "guest_boot": boot,
                "detail": "microvm_can_admit_runners=false",
                **microvm_status(),
            },
        }
    ok_argv, detail = validate_cli_argv(argv)
    if not ok_argv:
        return {
            "ok": False,
            "exit_code": 126,
            "stdout": "",
            "stderr": detail,
            "audit": {
                "backend": "microvm_track",
                "guest_boot": boot,
                "detail": detail,
                "allowlist": sorted(CLI_ALLOWLIST),
            },
        }
    to = timeout_s
    if to is None:
        try:
            to = float(os.environ.get("AIPLAT_EVAL_MICROVM_CLI_TIMEOUT_SEC") or "10")
        except ValueError:
            to = 10.0
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=to,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": "",
            "stderr": "timeout",
            "audit": {
                "backend": "microvm_track",
                "guest_boot": boot,
                "detail": "timeout",
                "argv": list(argv),
            },
        }
    ok = proc.returncode == 0
    return {
        "ok": ok,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "")[:8000],
        "stderr": (proc.stderr or "")[:2000],
        "audit": {
            "backend": "microvm_track",
            "guest_boot": boot,
            "isolation": "host_allowlist_under_microvm_policy",
            "kvm_available": True,
            "argv": list(argv),
            "honesty": (
                "host allowlist under microVM policy; "
                "guest_boot mirrors InstanceStart cache; "
                "sandbox_real_isolation=false"
            ),
        },
    }


def run_sandbox_probe_wrap() -> Dict[str, Any]:
    """Backend-aware ``true`` wrap for fixture runners (docker or microVM track)."""
    from app.sandbox.docker_exec import run_in_docker
    from app.sandbox.policy import sandbox_backend

    if sandbox_backend() == "microvm":
        return run_allowlisted_cli(["true"])
    return run_in_docker(["true"])


def _wire_microvm_exec() -> Dict[str, Any]:
    _ = probe_runtime
    _ = run_sandbox_probe_wrap
    return run_allowlisted_cli(["true"])
