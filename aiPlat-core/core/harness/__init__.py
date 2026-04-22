"""
Harness - Agent Framework
"""

from __future__ import annotations

# NOTE:
# This package intentionally avoids eager imports of heavy submodules.
#
# Historically `core.harness.__init__` imported `integration` (which imports execution/loop/tools),
# which created circular import risks for any code importing *any* `core.harness.*` submodule
# (e.g. `core.harness.kernel.runtime`).
#
# We expose the same public API via lazy attribute loading.

from importlib import import_module
from typing import Any

__all__ = [
    "HeartbeatMonitor",
    "heartbeat_monitor",
    "AgentStatus",
    "AgentHeartbeat",
    "AgentLifecycleState",
    "AgentState",
    "AgentStateEnum",
    "HarnessConfig",
    "HarnessIntegration",
    "create_harness",
    "get_harness",
    "coordination",
    "observability",
    "feedback_loops",
    "memory",
    "knowledge",
    "context",
]


_LAZY_ATTRS = {
    # state
    "AgentLifecycleState": ("core.harness.state", "AgentLifecycleState"),
    "AgentState": ("core.harness.state", "AgentState"),
    "AgentStateEnum": ("core.harness.state", "AgentStateEnum"),
    # heartbeat
    "HeartbeatMonitor": ("core.harness.heartbeat_monitor", "HeartbeatMonitor"),
    "heartbeat_monitor": ("core.harness.heartbeat_monitor", "heartbeat_monitor"),
    "AgentStatus": ("core.harness.heartbeat_monitor", "AgentStatus"),
    "AgentHeartbeat": ("core.harness.heartbeat_monitor", "AgentHeartbeat"),
    # integration
    "HarnessConfig": ("core.harness.integration", "HarnessConfig"),
    "HarnessIntegration": ("core.harness.integration", "HarnessIntegration"),
    "create_harness": ("core.harness.integration", "create_harness"),
    "get_harness": ("core.harness.integration", "get_harness"),
    # namespaces
    "coordination": ("core.harness", "coordination"),
    "observability": ("core.harness", "observability"),
    "feedback_loops": ("core.harness", "feedback_loops"),
    "memory": ("core.harness", "memory"),
    "knowledge": ("core.harness", "knowledge"),
    "context": ("core.harness", "context"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_ATTRS:
        mod_name, attr = _LAZY_ATTRS[name]
        if attr == name and mod_name == "core.harness":
            # subpackage/module passthrough
            return import_module(f"{mod_name}.{name}")
        return getattr(import_module(mod_name), attr)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + list(_LAZY_ATTRS.keys())))
