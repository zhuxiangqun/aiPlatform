"""
Kernel gates (Phase 3).

Gates are enforced at kernel boundaries (syscalls + integration.execute):
- PolicyGate: permission/approval
- TraceGate: spans + audit hooks
- ContextGate: token budget + compaction (placeholder in Phase 3)
- ResilienceGate: retry/timeout/fallback (minimal in Phase 3)
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

__all__ = [
    "PolicyGate",
    "PolicyDecision",
    "TraceGate",
    "TraceSpan",
    "ContextGate",
    "ResilienceGate",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    for mod in ("policy_gate", "trace_gate", "context_gate", "resilience_gate"):
        m = importlib.import_module(f"{__name__}.{mod}")
        if hasattr(m, name):
            return getattr(m, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))


if TYPE_CHECKING:
    from .context_gate import ContextGate
    from .policy_gate import PolicyDecision, PolicyGate
    from .resilience_gate import ResilienceGate
    from .trace_gate import TraceGate, TraceSpan
