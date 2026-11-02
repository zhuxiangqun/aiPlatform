"""B3-L sandbox admit policy.

Backends:
- ``off`` (default): sandbox runners stay ``sandbox_required``
- ``local_stub``: admit ``http_probe`` in-process (no network)
- ``docker``: admit ``http_probe`` (stub) + ``cli_probe`` + ``skill_suite`` fixture-only

Env: ``AIPLAT_EVAL_SANDBOX_BACKEND=off|local_stub|docker``
"""
from __future__ import annotations

import os
from typing import Any, Dict, Literal, Mapping, Optional

from app.sandbox.docker_exec import docker_available
from app.sandbox.skill_policy import skill_suite_is_fixture

SandboxBackend = Literal["off", "local_stub", "docker"]

B3_LOCAL_STUB_RUNNERS: frozenset[str] = frozenset({"http_probe"})
B3_DOCKER_RUNNERS: frozenset[str] = frozenset({"http_probe", "cli_probe", "skill_suite"})


def sandbox_backend() -> SandboxBackend:
    raw = (os.environ.get("AIPLAT_EVAL_SANDBOX_BACKEND") or "off").strip().lower()
    if raw in ("local_stub", "stub", "local"):
        return "local_stub"
    if raw in ("docker", "container"):
        return "docker"
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
        if rid in ("cli_probe", "skill_suite") and not docker_available():
            return False
        if rid == "skill_suite":
            return skill_suite_is_fixture(payload)
        return True
    return False


def sandbox_health() -> Dict[str, Any]:
    backend = sandbox_backend()
    admitted: list[str] = []
    if backend == "local_stub":
        admitted = sorted(B3_LOCAL_STUB_RUNNERS)
    elif backend == "docker":
        for r in sorted(B3_DOCKER_RUNNERS):
            if r in ("cli_probe", "skill_suite") and not docker_available():
                continue
            admitted.append(r if r != "skill_suite" else "skill_suite(fixture)")
    return {
        "b3l_sandbox": True,
        "sandbox_backend": backend,
        "sandbox_admitted_runners": admitted,
        "sandbox_real_isolation": False,
        "sandbox_isolation": (
            "container" if backend == "docker" else ("none" if backend == "off" else "process_stub")
        ),
        "docker_available": docker_available() if backend == "docker" else False,
        "skill_suite_real_tools": False,
        "note": (
            "B3-L sandbox prototype — docker network=none cli; "
            "skill_suite fixture-only (no live tools); not microVM; "
            "process_split_authorized=false."
        ),
    }


def _wire_policy() -> bool:
    """Same-file caller for method_verify."""
    _ = sandbox_health()
    return sandbox_admits("http_probe")
