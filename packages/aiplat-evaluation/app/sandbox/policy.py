"""B3-L sandbox admit policy.

Backends:
- ``off`` (default): sandbox runners stay ``sandbox_required``
- ``local_stub``: admit a tiny runner subset that runs **in-process stubs**
  (no network/shell/container). Proves enqueue→Worker plumbing only.

Env: ``AIPLAT_EVAL_SANDBOX_BACKEND=off|local_stub``
"""
from __future__ import annotations

import os
from typing import Any, Dict, Literal

SandboxBackend = Literal["off", "local_stub"]

# First B3-L slice: http_probe stub only (no fetch). Others stay sandbox_required.
B3_LOCAL_STUB_RUNNERS: frozenset[str] = frozenset({"http_probe"})


def sandbox_backend() -> SandboxBackend:
    raw = (os.environ.get("AIPLAT_EVAL_SANDBOX_BACKEND") or "off").strip().lower()
    if raw in ("local_stub", "stub", "local"):
        return "local_stub"
    return "off"


def sandbox_admits(runner_id: str) -> bool:
    """True when this runner may enqueue+execute under current sandbox backend."""
    rid = (runner_id or "").strip()
    if not rid:
        return False
    if sandbox_backend() != "local_stub":
        return False
    return rid in B3_LOCAL_STUB_RUNNERS


def sandbox_health() -> Dict[str, Any]:
    backend = sandbox_backend()
    return {
        "b3l_sandbox": True,
        "sandbox_backend": backend,
        "sandbox_admitted_runners": sorted(B3_LOCAL_STUB_RUNNERS) if backend == "local_stub" else [],
        "sandbox_real_isolation": False,
        "note": (
            "B3-L local_stub only — no container/microVM; "
            "process_split_authorized=false."
        ),
    }


def _wire_policy() -> bool:
    """Same-file caller for method_verify."""
    _ = sandbox_health()
    return sandbox_admits("http_probe")
