"""microVM readiness + Linux/KVM track probe.

Honesty:
- Default **not ready** on developer laptops (esp. Darwin without KVM).
- Never sets ``process_split_authorized=true``.
- Never sets ``skill_suite_real_tools=true`` / live attacks in this slice.
- ``sandbox_real_isolation`` stays **false** (not a certification).
- Runner admit under backend=microvm requires Linux+KVM+binary+enable
  **and** ``AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS=1`` (see MICROVM_LINUX_TRACK.md).
- Guest rootfs/Firecracker boot is optional later; v1 may run allowlisted
  host CLI under microVM **policy** with ``guest_boot=false``.
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


def kvm_available() -> bool:
    """Linux KVM device present (not available on Darwin)."""
    if platform.system().lower() != "linux":
        return False
    return os.path.exists("/dev/kvm")


def microvm_admit_runners_enabled() -> bool:
    raw = (os.environ.get("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def microvm_ready() -> bool:
    """Binary present + explicit enable. Still ≠ live-tools unlock; ≠ host_ok alone."""
    return microvm_enabled() and microvm_available()


def microvm_host_ok() -> bool:
    """Linux track host: enabled + binary + KVM.

    Darwin always False (no /dev/kvm).
    """
    return (
        platform.system().lower() == "linux"
        and microvm_ready()
        and kvm_available()
    )


def microvm_can_admit_runners() -> bool:
    """Policy may admit non-live runners under backend=microvm."""
    return microvm_host_ok() and microvm_admit_runners_enabled()


def microvm_block_reason() -> str:
    if microvm_can_admit_runners():
        return "linux_track_admit_ready_guest_boot_deferred"
    if microvm_host_ok() and not microvm_admit_runners_enabled():
        return "host_ok_admit_runners_flag_off"
    if microvm_ready() and not kvm_available():
        sysname = platform.system().lower()
        if sysname == "darwin":
            return "microvm_ready_but_darwin_no_kvm"
        return "microvm_ready_but_kvm_missing"
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
    host_ok = microvm_host_ok()
    admit = microvm_can_admit_runners()
    return {
        "microvm_available": microvm_available(),
        "microvm_enabled": microvm_enabled(),
        "microvm_ready": ready,
        "kvm_available": kvm_available(),
        "microvm_host_ok": host_ok,
        "microvm_admit_runners": admit,
        "microvm_bin": microvm_bin(),
        "microvm_block_reason": microvm_block_reason(),
        "sandbox_real_isolation": False,
        "skill_suite_real_tools": False,
        "security_live_attacks": False,
        "guest_boot": False,
        "process_split_authorized": False,
        "platform": platform.system().lower(),
        "eligible_on_darwin": False,
        "honesty": (
            "microVM Linux/KVM track v1 — admit non-live runners only when "
            "host_ok+ADMIT_RUNNERS; guest Firecracker boot deferred; "
            "sandbox_real_isolation=false; live skill tools denied; "
            "not staging authorize; not G2b accuracy"
        ),
    }


def _wire_microvm() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    _ = microvm_available()
    _ = kvm_available()
    _ = microvm_host_ok()
    _ = microvm_can_admit_runners()
    _ = microvm_block_reason()
    return microvm_status()
