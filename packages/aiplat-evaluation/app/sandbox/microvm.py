"""microVM readiness probe — prep only (no live skill tools).

Honesty:
- Default **not ready** on developer laptops (esp. Darwin without KVM).
- Never sets ``sandbox_real_isolation=true`` or ``skill_suite_real_tools=true``.
- Enabling requires both an executable binary **and** explicit
  ``AIPLAT_EVAL_MICROVM_ENABLED=1`` — still does **not** admit live tools
  until a later unlock slice (see ``docs/a3/MICROVM_PREP.md``).
- ``process_split_authorized`` stays false.
"""
from __future__ import annotations

import os
import platform
import shutil
from typing import Any, Dict


def microvm_bin() -> str:
    return (os.environ.get("AIPLAT_EVAL_MICROVM_BIN") or "firecracker").strip() or "firecracker"


def microvm_available() -> bool:
    """True when a microVM runtime binary is on PATH or an absolute executable."""
    path = microvm_bin()
    if os.path.isabs(path) and os.path.isfile(path) and os.access(path, os.X_OK):
        return True
    return shutil.which(path) is not None


def microvm_enabled() -> bool:
    raw = (os.environ.get("AIPLAT_EVAL_MICROVM_ENABLED") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def microvm_ready() -> bool:
    """Runtime present + explicit enable. Still ≠ live-tools unlock."""
    return microvm_enabled() and microvm_available()


def microvm_block_reason() -> str:
    if microvm_ready():
        return "prep_only_live_tools_locked"
    if not microvm_enabled():
        return "microvm_not_enabled"
    if not microvm_available():
        sysname = platform.system().lower()
        if sysname == "darwin":
            return "microvm_bin_missing_darwin_no_kvm"
        return "microvm_bin_missing"
    return "microvm_not_ready"


def microvm_status() -> Dict[str, Any]:
    ready = microvm_ready()
    return {
        "microvm_available": microvm_available(),
        "microvm_enabled": microvm_enabled(),
        "microvm_ready": ready,
        "microvm_bin": microvm_bin(),
        "microvm_block_reason": microvm_block_reason(),
        "sandbox_real_isolation": False,
        "skill_suite_real_tools": False,
        "security_live_attacks": False,
        "process_split_authorized": False,
        "platform": platform.system().lower(),
        "honesty": (
            "microVM prep probe only — live skill tools stay denied; "
            "not staging authorize; not G2b accuracy"
        ),
    }


def _wire_microvm() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    _ = microvm_available()
    _ = microvm_block_reason()
    return microvm_status()
