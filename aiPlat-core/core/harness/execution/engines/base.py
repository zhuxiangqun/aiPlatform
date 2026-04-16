"""
Engine contracts (Phase 5).

Phase 5.0 goal:
- Introduce an EngineRouter without changing runtime behavior.
- Engines should NOT implement governance themselves; syscalls/gates remain the choke points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class EngineDecision:
    """
    Router decision.

    - engine: selected engine id (e.g., "loop", "langgraph")
    - explain: human-readable explanation for observability/audit
    - fallback_chain: planned fallback order (Phase 5.1+)
    """

    engine: str
    explain: str
    fallback_chain: List[str] = field(default_factory=list)
    # fallback_trace: execution-time trace of routing attempts (Phase 5.1+).
    # Each item is a JSON-serializable dict, e.g.:
    # {"engine": "loop", "status": "selected|failed|skipped", "reason": "...", "ts": 123.4}
    fallback_trace: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class IExecutionEngine(Protocol):
    """Minimal engine interface."""

    name: str

    async def execute_agent(self, agent: Any, context: Any) -> Any:  # returns AgentResult
        ...
