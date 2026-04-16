"""
ContextAssembler (Phase 4 - placeholder).

Phase 4 To-Be:
- Build PromptContext with token budgeting, compaction, and source attribution.

Phase 4 (minimal):
- Provide a stable interface and metadata output, without modifying content.
- Actual truncation guardrails remain in ContextGate (Phase 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextAssemblyResult:
    messages: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContextAssembler:
    def assemble(
        self,
        messages: List[Dict[str, Any]],
        *,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextAssemblyResult:
        meta = dict(metadata or {})
        if session_id:
            meta.setdefault("session_id", session_id)
        if user_id:
            meta.setdefault("user_id", user_id)
        meta.setdefault("phase", "4-minimal")
        return ContextAssemblyResult(messages=messages, metadata=meta)

