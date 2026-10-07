"""Observability contract — declared production stack for agent ops.

Contract (v1): Prometheus process metrics + EventBus + run_graph / syscall traces.
ELK/OpenSearch is NOT part of the contract; ops may add it externally.

callers: diagnostics._check_observability_contract, CoreFacade.get_observability_contract
"""

from __future__ import annotations

from typing import Any, Dict, List


CONTRACT_VERSION = "1.0"

# Explicit: what production MTTR depends on vs what is optional.
DECLARED_STACK: List[Dict[str, str]] = [
    {
        "component": "prometheus",
        "role": "process_metrics",
        "status": "required",
        "anchor": "prometheus-fastapi-instrumentator / infra monitoring",
    },
    {
        "component": "event_bus",
        "role": "run_sse_events",
        "status": "required",
        "anchor": "core/harness/observation/event_bus.py",
    },
    {
        "component": "run_graph",
        "role": "execution_graph",
        "status": "required",
        "anchor": "core/harness/observation/run_graph.py",
    },
    {
        "component": "syscall_events",
        "role": "durable_trace",
        "status": "required",
        "anchor": "execution_store.syscall_events",
    },
    {
        "component": "elk_opensearch",
        "role": "central_log_search",
        "status": "out_of_contract",
        "anchor": "optional external; not shipped as agent OS dependency",
    },
]


def get_observability_contract() -> Dict[str, Any]:
    """Return the declared observability contract (static + import probes)."""
    probes: Dict[str, Any] = {}
    try:
        from core.harness.observation.event_bus import EventBus  # noqa: F401
        probes["event_bus"] = "ok"
    except Exception as e:
        probes["event_bus"] = f"error:{type(e).__name__}"
    try:
        from core.harness.observation import run_graph  # noqa: F401
        probes["run_graph"] = "ok"
    except Exception as e:
        probes["run_graph"] = f"error:{type(e).__name__}"
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        probes["execution_store"] = "ok" if store is not None else "missing"
    except Exception as e:
        probes["execution_store"] = f"error:{type(e).__name__}"

    required_ok = all(
        probes.get(k, "").startswith("ok") or probes.get(k) == "ok"
        for k in ("event_bus", "run_graph", "execution_store")
    )
    return {
        "version": CONTRACT_VERSION,
        "stack": DECLARED_STACK,
        "probes": probes,
        "healthy": required_ok,
        "note": (
            "Production agent observability = Prometheus + EventBus + run_graph "
            "+ syscall_events. ELK is out of contract."
        ),
    }
