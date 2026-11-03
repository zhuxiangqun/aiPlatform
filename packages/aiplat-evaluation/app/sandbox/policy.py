"""B3-L / S1 sandbox admit policy.

Backends:
- ``off`` (default): sandbox runners stay ``sandbox_required``
- ``local_stub``: admit ``http_probe`` in-process (no network)
- ``docker``: http_probe + cli_probe + skill_suite fixture + security_redteam fixture
- ``microvm``: Linux/KVM track — admit non-live runners only when
  ``microvm_can_admit_runners()`` (host_ok + ADMIT_RUNNERS); else prep deny-all

Env: ``AIPLAT_EVAL_SANDBOX_BACKEND=off|local_stub|docker|microvm``
"""
from __future__ import annotations

import os
from typing import Any, Dict, Literal, Mapping, Optional

from app.sandbox.docker_exec import docker_available
from app.sandbox.microvm import microvm_can_admit_runners, microvm_status
from app.sandbox.microvm_exec import probe_runtime
from app.sandbox.security_policy import (
    s1_live_enabled,
    security_redteam_admits,
    security_redteam_is_fixture,
)
from app.sandbox.skill_policy import skill_suite_is_fixture

SandboxBackend = Literal["off", "local_stub", "docker", "microvm"]

B3_LOCAL_STUB_RUNNERS: frozenset[str] = frozenset({"http_probe"})
B3_DOCKER_RUNNERS: frozenset[str] = frozenset(
    {"http_probe", "cli_probe", "skill_suite", "security_redteam"}
)
# Same non-live surface as docker when Linux microVM track admits.
B3_MICROVM_RUNNERS: frozenset[str] = B3_DOCKER_RUNNERS
_DOCKER_NEEDS_BIN = frozenset({"cli_probe", "skill_suite", "security_redteam"})


def sandbox_backend() -> SandboxBackend:
    raw = (os.environ.get("AIPLAT_EVAL_SANDBOX_BACKEND") or "off").strip().lower()
    if raw in ("local_stub", "stub", "local"):
        return "local_stub"
    if raw in ("docker", "container"):
        return "docker"
    if raw in ("microvm", "firecracker", "kvm"):
        return "microvm"
    return "off"


def sandbox_admits(
    runner_id: str,
    *,
    payload: Optional[Mapping[str, Any]] = None,
) -> bool:
    """True when this runner may enqueue+execute under current sandbox backend."""
    rid = (runner_id or "").strip()
    if not rid:
        return False
    backend = sandbox_backend()
    if backend == "local_stub":
        return rid in B3_LOCAL_STUB_RUNNERS
    if backend == "docker":
        if rid not in B3_DOCKER_RUNNERS:
            return False
        if rid in _DOCKER_NEEDS_BIN and not docker_available():
            return False
        if rid == "skill_suite":
            return skill_suite_is_fixture(payload)
        if rid == "security_redteam":
            return security_redteam_admits(payload)
        return True
    if backend == "microvm":
        # Live skill tools stay denied via skill_suite_is_fixture / security policy.
        if not microvm_can_admit_runners():
            return False
        if rid not in B3_MICROVM_RUNNERS:
            return False
        if rid == "skill_suite":
            return skill_suite_is_fixture(payload)
        if rid == "security_redteam":
            # microVM track v1: fixture only (no live_llm / live tools).
            return security_redteam_is_fixture(payload)
        return True
    return False


def sandbox_health() -> Dict[str, Any]:
    backend = sandbox_backend()
    admitted: list[str] = []
    if backend == "local_stub":
        admitted = sorted(B3_LOCAL_STUB_RUNNERS)
    elif backend == "docker":
        for r in sorted(B3_DOCKER_RUNNERS):
            if r in _DOCKER_NEEDS_BIN and not docker_available():
                continue
            if r == "skill_suite":
                admitted.append("skill_suite(fixture)")
            elif r == "security_redteam":
                if s1_live_enabled():
                    admitted.append("security_redteam(fixture|live_llm)")
                else:
                    admitted.append("security_redteam(fixture)")
            else:
                admitted.append(r)
    elif backend == "microvm":
        if microvm_can_admit_runners():
            for r in sorted(B3_MICROVM_RUNNERS):
                if r == "skill_suite":
                    admitted.append("skill_suite(fixture)")
                elif r == "security_redteam":
                    admitted.append("security_redteam(fixture)")
                else:
                    admitted.append(r)
        else:
            admitted = []
    mvm = microvm_status()
    isolation = "none"
    if backend == "docker":
        isolation = "container"
    elif backend == "local_stub":
        isolation = "process_stub"
    elif backend == "microvm":
        isolation = (
            "microvm_linux_track"
            if microvm_can_admit_runners()
            else "microvm_prep"
        )
    runtime_probe_ok: bool | None = None
    if backend == "microvm" and mvm.get("microvm_available"):
        runtime_probe_ok = bool(probe_runtime().get("ok"))
    return {
        "b3l_sandbox": True,
        "s1_security_eval": True,
        "sandbox_backend": backend,
        "sandbox_admitted_runners": admitted,
        "sandbox_real_isolation": False,
        "sandbox_isolation": isolation,
        "docker_available": docker_available() if backend == "docker" else False,
        "skill_suite_real_tools": False,
        # True only when env-gated live_llm path is unlocked (still ≠ security cert).
        "security_live_attacks": bool(s1_live_enabled() and backend == "docker"),
        "microvm_available": mvm["microvm_available"],
        "microvm_enabled": mvm["microvm_enabled"],
        "microvm_ready": mvm["microvm_ready"],
        "microvm_host_ok": mvm["microvm_host_ok"],
        "microvm_admit_runners": mvm["microvm_admit_runners"],
        "kvm_available": mvm["kvm_available"],
        "microvm_block_reason": mvm["microvm_block_reason"],
        "microvm_runtime_probe_ok": runtime_probe_ok,
        "guest_boot": False,
        "note": (
            "B3-L/S1 sandbox — docker network=none; skill fixture-only / no live tools; "
            "security fixture default; live_llm opt-in via AIPLAT_EVAL_S1_LIVE=1 on docker; "
            "microVM Linux/KVM track admits non-live runners when host_ok+ADMIT_RUNNERS; "
            "guest_boot deferred; process_split_authorized=false; not a security certification."
        ),
    }


def _wire_policy() -> bool:
    """Same-file caller for method_verify."""
    _ = sandbox_health()
    return sandbox_admits("http_probe")
