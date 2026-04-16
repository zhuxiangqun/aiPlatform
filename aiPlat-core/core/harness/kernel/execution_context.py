"""
Execution context variables (Phase 6.8).

We use contextvars to safely pass per-request execution metadata (like active release)
down to low-level syscalls (e.g. sys_llm_generate) without changing every call site.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Optional
import time


@dataclass
class ActiveReleaseContext:
    target_type: str
    target_id: str
    candidate_id: str
    version: str
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "candidate_id": self.candidate_id,
            "version": self.version,
            "summary": self.summary,
        }


_active_release_ctx: ContextVar[Optional[ActiveReleaseContext]] = ContextVar("active_release_ctx", default=None)


def set_active_release_context(ctx: Optional[ActiveReleaseContext]):
    """Set active release context for current async task. Returns a token for reset()."""
    return _active_release_ctx.set(ctx)


def reset_active_release_context(token) -> None:
    """Reset to previous value using token returned by set_active_release_context()."""
    _active_release_ctx.reset(token)


def get_active_release_context() -> Optional[ActiveReleaseContext]:
    return _active_release_ctx.get()


# ---------------------------------------------------------------------------
# Prompt revision audit (Phase 6.12)
# ---------------------------------------------------------------------------


@dataclass
class PromptRevisionAudit:
    """Aggregated prompt revision application info for one execution."""

    applied_ids: list[str]
    ignored_ids: list[str]
    conflicts: list[dict]
    llm_calls: int = 0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applied_prompt_revision_ids": list(self.applied_ids),
            "ignored_prompt_revision_ids": list(self.ignored_ids),
            "prompt_revision_conflicts": list(self.conflicts),
            "llm_calls": int(self.llm_calls),
            "updated_at": float(self.updated_at),
        }


_prompt_revision_audit_ctx: ContextVar[Optional[PromptRevisionAudit]] = ContextVar("prompt_revision_audit_ctx", default=None)


def set_prompt_revision_audit(audit: Optional[PromptRevisionAudit]):
    return _prompt_revision_audit_ctx.set(audit)


def reset_prompt_revision_audit(token) -> None:
    _prompt_revision_audit_ctx.reset(token)


def get_prompt_revision_audit() -> Optional[PromptRevisionAudit]:
    return _prompt_revision_audit_ctx.get()


def record_prompt_revision_application(
    *,
    applied_ids: list[str],
    ignored_ids: list[str],
    conflicts: list[dict],
) -> None:
    """
    Best-effort aggregation used by sys_llm_generate.
    """
    audit = _prompt_revision_audit_ctx.get()
    if audit is None:
        return
    audit.llm_calls += 1
    audit.updated_at = time.time()
    # Preserve order of first appearance
    for x in applied_ids or []:
        if isinstance(x, str) and x and x not in audit.applied_ids:
            audit.applied_ids.append(x)
    for x in ignored_ids or []:
        if isinstance(x, str) and x and x not in audit.ignored_ids:
            audit.ignored_ids.append(x)
    # Keep conflicts as a growing list (dedupe best-effort by JSON repr)
    seen = {str(c) for c in audit.conflicts}
    for c in conflicts or []:
        k = str(c)
        if k not in seen:
            audit.conflicts.append(c)
            seen.add(k)
