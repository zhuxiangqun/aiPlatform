"""B3-L sandbox policy (local_stub / docker / microVM Linux track).

Honesty: local engineering only; microVM guest_boot requires explicit authorize;
live skill tools denied; process_split_authorized=false.
"""
from __future__ import annotations

from app.sandbox.guest_boot import probe_guest_boot
from app.sandbox.microvm import (
    clear_guest_boot_cache,
    guest_boot_cached,
    kvm_available,
    microvm_can_admit_runners,
    microvm_guest_boot_authorized,
    microvm_host_ok,
    microvm_ready,
    microvm_status,
    set_guest_boot_cache,
)
from app.sandbox.policy import (
    B3_DOCKER_RUNNERS,
    B3_LOCAL_STUB_RUNNERS,
    B3_MICROVM_RUNNERS,
    sandbox_admits,
    sandbox_backend,
    sandbox_health,
)
from app.sandbox.security_policy import (
    s1_live_enabled,
    security_redteam_admits,
    security_redteam_is_fixture,
    security_redteam_is_live_llm,
)
from app.sandbox.skill_policy import skill_suite_is_fixture

__all__ = [
    "B3_DOCKER_RUNNERS",
    "B3_LOCAL_STUB_RUNNERS",
    "B3_MICROVM_RUNNERS",
    "clear_guest_boot_cache",
    "guest_boot_cached",
    "kvm_available",
    "microvm_can_admit_runners",
    "microvm_guest_boot_authorized",
    "microvm_host_ok",
    "microvm_ready",
    "microvm_status",
    "probe_guest_boot",
    "s1_live_enabled",
    "sandbox_admits",
    "sandbox_backend",
    "sandbox_health",
    "security_redteam_admits",
    "security_redteam_is_fixture",
    "security_redteam_is_live_llm",
    "set_guest_boot_cache",
    "skill_suite_is_fixture",
]
