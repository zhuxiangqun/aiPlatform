"""B3-L / S1 sandbox admit policy.

Backends:
- ``off`` (default): sandbox runners stay ``sandbox_required``
- ``local_stub``: admit ``http_probe`` in-process (no network)
- ``docker``: http_probe + cli_probe + skill_suite fixture + security_redteam fixture
- ``microvm``: **prep only** — admits **nothing** (live tools stay locked)

Env: ``AIPLAT_EVAL_SANDBOX_BACKEND=off|local_stub|docker|microvm``
"""
from __future__ import annotations

import os
from typing import Any, Dict, Literal, Mapping, Optional

from app.sandbox.docker_exec import docker_available
from app.sandbox.microvm import microvm_status
from app.sandbox.security_policy import s1_live_enabled, security_redteam_admits
from app.sandbox.skill_policy import skill_suite_is_fixture

SandboxBackend = Literal["off", "local_stub", "docker", "microvm"]

B3_LOCAL_STUB_RUNNERS: frozenset[str] = frozenset({"http_probe"})
B3_DOCKER_RUNNERS: frozenset[str] = frozenset(
    {"http_probe", "cli_probe", "skill_suite", "security_redteam"}
)
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
        # Prep slice: never admit runners (incl. live skill tools).
        return False
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
        admitted = []
    mvm = microvm_status()
    isolation = "none"
    if backend == "docker":
        isolation = "container"
    elif backend == "local_stub":
        isolation = "process_stub"
    elif backend == "microvm":
        isolation = "microvm_prep"
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
        "microvm_block_reason": mvm["microvm_block_reason"],
        "note": (
            "B3-L/S1 sandbox — docker network=none; skill fixture-only / no live tools; "
            "security fixture default; live_llm opt-in via AIPLAT_EVAL_S1_LIVE=1; "
            "microVM prep only; process_split_authorized=false; not a security certification."
        ),
    }


def _wire_policy() -> bool:
    """Same-file caller for method_verify."""
    _ = sandbox_health()
    return sandbox_admits("http_probe")
