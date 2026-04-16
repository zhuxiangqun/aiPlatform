"""
Kernel gates (Phase 3).

Gates are enforced at kernel boundaries (syscalls + integration.execute):
- PolicyGate: permission/approval
- TraceGate: spans + audit hooks
- ContextGate: token budget + compaction (placeholder in Phase 3)
- ResilienceGate: retry/timeout/fallback (minimal in Phase 3)
"""

from .policy_gate import PolicyGate, PolicyDecision
from .trace_gate import TraceGate, TraceSpan
from .context_gate import ContextGate
from .resilience_gate import ResilienceGate

__all__ = [
    "PolicyGate",
    "PolicyDecision",
    "TraceGate",
    "TraceSpan",
    "ContextGate",
    "ResilienceGate",
]

