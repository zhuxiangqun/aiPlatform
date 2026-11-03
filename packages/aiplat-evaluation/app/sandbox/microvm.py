"""microVM readiness + Linux/KVM track + guest_boot authorize probe.

Honesty:
- Default **not ready** on developer laptops (esp. Darwin without KVM).
- Never sets ``process_split_authorized=true``.
- Never sets ``skill_suite_real_tools=true`` / live attacks in this slice.
- ``sandbox_real_isolation`` stays **false** (not a certification).
- Runner admit under backend=microvm requires Linux+KVM+binary+enable
  **and** ``AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS=1`` (see MICROVM_LINUX_TRACK.md).
- Guest Firecracker boot requires host_ok + ``AIPLAT_EVAL_MICROVM_GUEST_BOOT=1``
  + kernel/rootfs assets (see MICROVM_GUEST_BOOT.md). ``guest_boot=true`` only
  after a successful InstanceStart probe (cached for the process).
"""
from __future__ import annotations

import os
import platform
import shutil
from typing import Any, Dict, Optional, Tuple

_GUEST_BOOT_CACHE: Optional[bool] = None


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


def microvm_guest_boot_flag() -> bool:
    """Explicit authorize for guest boot attempts (≠ process_split_authorized)."""
    raw = (os.environ.get("AIPLAT_EVAL_MICROVM_GUEST_BOOT") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def microvm_guest_assets() -> Tuple[Optional[str], Optional[str]]:
    """Return (kernel_path, rootfs_path) when both files exist; else (None, None)."""
    kernel = (os.environ.get("AIPLAT_EVAL_MICROVM_KERNEL") or "").strip()
    rootfs = (os.environ.get("AIPLAT_EVAL_MICROVM_ROOTFS") or "").strip()
    if not kernel or not rootfs:
        return None, None
    if not (os.path.isfile(kernel) and os.path.isfile(rootfs)):
        return None, None
    return kernel, rootfs


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


def microvm_guest_boot_authorized() -> bool:
    """May attempt Firecracker guest boot (host_ok + flag + assets).

    This is the microVM-track **authorize** surface for guest_boot.
    It does **not** flip ``process_split_authorized`` / staging.
    """
    kernel, rootfs = microvm_guest_assets()
    return bool(
        microvm_host_ok()
        and microvm_guest_boot_flag()
        and kernel
        and rootfs
    )


def guest_boot_cached() -> bool:
    """True only after a successful InstanceStart in this process (see probe)."""
    return bool(_GUEST_BOOT_CACHE)


def set_guest_boot_cache(ok: bool) -> None:
    """Record probe outcome for health/status (tests may call directly)."""
    global _GUEST_BOOT_CACHE
    _GUEST_BOOT_CACHE = bool(ok)


def clear_guest_boot_cache() -> None:
    global _GUEST_BOOT_CACHE
    _GUEST_BOOT_CACHE = None


def microvm_block_reason() -> str:
    if guest_boot_cached():
        return "linux_track_guest_boot_ok"
    if microvm_guest_boot_authorized():
        return "linux_track_guest_boot_authorized_pending_probe"
    if microvm_guest_boot_flag() and microvm_host_ok() and not microvm_guest_assets()[0]:
        return "guest_boot_flag_on_assets_missing"
    if microvm_can_admit_runners() and not microvm_guest_boot_flag():
        return "linux_track_admit_ready_guest_boot_flag_off"
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
    boot_auth = microvm_guest_boot_authorized()
    kernel, rootfs = microvm_guest_assets()
    boot_ok = guest_boot_cached()
    return {
        "microvm_available": microvm_available(),
        "microvm_enabled": microvm_enabled(),
        "microvm_ready": ready,
        "kvm_available": kvm_available(),
        "microvm_host_ok": host_ok,
        "microvm_admit_runners": admit,
        "guest_boot_flag": microvm_guest_boot_flag(),
        "guest_boot_authorized": boot_auth,
        "guest_boot_assets": bool(kernel and rootfs),
        "guest_boot_kernel": kernel,
        "guest_boot_rootfs": rootfs,
        "microvm_bin": microvm_bin(),
        "microvm_block_reason": microvm_block_reason(),
        "sandbox_real_isolation": False,
        "skill_suite_real_tools": False,
        "security_live_attacks": False,
        "guest_boot": boot_ok,
        "process_split_authorized": False,
        "platform": platform.system().lower(),
        "eligible_on_darwin": False,
        "honesty": (
            "microVM Linux/KVM track — admit non-live runners when host_ok+ADMIT_RUNNERS; "
            "guest_boot authorize via GUEST_BOOT=1+KERNEL+ROOTFS; guest_boot=true only after "
            "InstanceStart probe; sandbox_real_isolation=false; live skill tools denied; "
            "process_split_authorized=false (staging checklist still required); not G2b accuracy"
        ),
    }


def _wire_microvm() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    _ = microvm_available()
    _ = kvm_available()
    _ = microvm_host_ok()
    _ = microvm_can_admit_runners()
    _ = microvm_guest_boot_authorized()
    _ = microvm_block_reason()
    return microvm_status()
