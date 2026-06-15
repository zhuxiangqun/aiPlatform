"""
Execution context variables (Phase 6.8).

We use contextvars to safely pass per-request execution metadata (like active release)
down to low-level syscalls (e.g. sys_llm_generate) without changing every call site.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Optional, List
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

@dataclass
class ActiveWorkspaceContext:
    """
    Per-execution workspace context (Phase R1).

    Purpose:
    - Provide repo/workspace metadata to low-level syscalls (e.g. sys_llm_generate)
      without having to thread it through every call site.
    """

    repo_root: Optional[str] = None
    context_file: Optional[str] = None
    project_context: str = ""
    toolset: Optional[str] = None
    mcp_ids: Optional[List[str]] = None
    agent_ids: Optional[List[str]] = None
    workflow_ids: Optional[List[str]] = None
    # Optional: multiple CLAUDE.md files for multi-repo / multi-path operations.
    claude_md_files: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "context_file": self.context_file,
            "project_context": self.project_context,
            "toolset": self.toolset,
            "claude_md_files": list(self.claude_md_files or []) if self.claude_md_files else None,
        }


_active_workspace_ctx: ContextVar[Optional[ActiveWorkspaceContext]] = ContextVar(
    "active_workspace_ctx", default=None
)


def set_active_workspace_context(ctx: Optional[ActiveWorkspaceContext]):
    """Set active workspace context for current async task. Returns a token for reset()."""
    return _active_workspace_ctx.set(ctx)


def reset_active_workspace_context(token) -> None:
    """Reset to previous value using token returned by set_active_workspace_context()."""
    _active_workspace_ctx.reset(token)


def get_active_workspace_context() -> Optional[ActiveWorkspaceContext]:
    return _active_workspace_ctx.get()


# ── GateTracer: runtime gate coverage tracking (Phase 3) ──
# Marks which mandatory gates were passed during an execution.
# Validated at exit time to detect runtime gate bypasses.

_gate_coverage: ContextVar[set] = ContextVar("_gate_coverage", default=set())


def mark_gate_passed(gate_name: str) -> None:
    """Mark a mandatory gate as passed for the current execution."""
    _gate_coverage.get().add(gate_name)


def get_gate_coverage() -> set:
    """Get the set of gates passed in the current execution scope."""
    return _gate_coverage.get().copy()


def reset_gate_coverage() -> Any:
    """Start a fresh gate coverage scope. Returns token for restore."""
    token = _gate_coverage.set(set())
    return token


# ---------------------------------------------------------------------------
# Approval context (P4): propagate approval_request_id across nested calls
# ---------------------------------------------------------------------------

_active_approval_request_id: ContextVar[Optional[str]] = ContextVar("active_approval_request_id", default=None)


def set_active_approval_request_id(approval_request_id: Optional[str]):
    """Set current approval_request_id for nested syscalls. Returns a token for reset()."""
    return _active_approval_request_id.set(str(approval_request_id) if approval_request_id else None)


def reset_active_approval_request_id(token) -> None:
    _active_approval_request_id.reset(token)


def get_active_approval_request_id() -> Optional[str]:
    return _active_approval_request_id.get()


# ---------------------------------------------------------------------------
# Tenant policy snapshot (P5): load once per execution, used by syscalls
# ---------------------------------------------------------------------------


@dataclass
class ActiveTenantPolicyContext:
    tenant_id: Optional[str]
    version: Optional[int]
    policy: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "version": self.version,
            "policy": self.policy or {},
        }


_active_tenant_policy_ctx: ContextVar[Optional[ActiveTenantPolicyContext]] = ContextVar(
    "active_tenant_policy_ctx", default=None
)


def set_active_tenant_policy_context(ctx: Optional[ActiveTenantPolicyContext]):
    return _active_tenant_policy_ctx.set(ctx)


def reset_active_tenant_policy_context(token) -> None:
    _active_tenant_policy_ctx.reset(token)


def get_active_tenant_policy_context() -> Optional[ActiveTenantPolicyContext]:
    return _active_tenant_policy_ctx.get()


@dataclass
class ActiveRequestContext:
    """
    Per-request identity context (Roadmap R4: session search / memory injection).
    """

    user_id: str = "system"
    session_id: str = "default"
    channel: Optional[str] = None
    # PR-01: tenant/actor context (platformization)
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    entrypoint: Optional[str] = None
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "channel": self.channel,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "entrypoint": self.entrypoint,
            "request_id": self.request_id,
        }


_active_request_ctx: ContextVar[Optional[ActiveRequestContext]] = ContextVar("active_request_ctx", default=None)


def set_active_request_context(ctx: Optional[ActiveRequestContext]):
    """Set active request context for current async task. Returns a token for reset()."""
    return _active_request_ctx.set(ctx)


def reset_active_request_context(token) -> None:
    """Reset to previous value using token returned by set_active_request_context()."""
    _active_request_ctx.reset(token)


def get_active_request_context() -> Optional[ActiveRequestContext]:
    return _active_request_ctx.get()


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


# ---------------------------------------------------------------------------
# Change contract (Phase 7.2 - Diff Gate)
# ---------------------------------------------------------------------------


@dataclass
class ActiveChangeContract:
    """
    Captured from a coding/executable skill output to gate follow-up repo mutations.
    """

    source_skill: str = ""
    changed_files: List[str] = None
    unrelated_changes: Optional[bool] = None
    acceptance_criteria: List[str] = None
    change_plan: str = ""
    rollback_plan: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_skill": self.source_skill,
            "changed_files": list(self.changed_files or []),
            "unrelated_changes": self.unrelated_changes,
            "acceptance_criteria": list(self.acceptance_criteria or []),
            "change_plan": self.change_plan,
            "rollback_plan": self.rollback_plan,
            "updated_at": float(self.updated_at or 0.0),
        }


_change_contract_ctx: ContextVar[Optional[ActiveChangeContract]] = ContextVar("change_contract_ctx", default=None)


def set_active_change_contract(contract: Optional[ActiveChangeContract]):
    """Set active change contract for current async task. Returns a token for reset()."""
    return _change_contract_ctx.set(contract)


def reset_active_change_contract(token) -> None:
    _change_contract_ctx.reset(token)


def get_active_change_contract() -> Optional[ActiveChangeContract]:
    return _change_contract_ctx.get()


# ---------------------------------------------------------------------------
# ActiveTraceContext — per-execution trace context for downstream event emission
# ---------------------------------------------------------------------------
# Handler Skills, Workflow Code nodes, MCP adapters, and any other code that
# runs outside the syscall boundary need a way to emit observable events
# through the unified add_syscall_event → SQLite + EventBus + SSE pipeline.
#
# This context is set by every syscall entry point (sys_skill_call, sys_tool_call,
# sys_llm_generate, sys_agent_call) before delegating to downstream code.
# Downstream code calls emit_trace_event() — a one-liner that reads the context
# and calls add_syscall_event() automatically.


@dataclass
class ActiveTraceContext:
    run_id: str
    span_id: str
    parent_span_id: str = ""


_active_trace_ctx: ContextVar[Optional[ActiveTraceContext]] = ContextVar("active_trace_ctx", default=None)


def set_active_trace_context(ctx: Optional[ActiveTraceContext]):
    """Set active trace context for current async task. Returns a token for reset()."""
    return _active_trace_ctx.set(ctx)


def reset_active_trace_context(token) -> None:
    """Reset to previous value using token returned by set_active_trace_context()."""
    _active_trace_ctx.reset(token)


def get_active_trace_context() -> Optional[ActiveTraceContext]:
    return _active_trace_ctx.get()


async def emit_trace_event_async(
    kind: str,
    name: str,
    status: str = "completed",
    *,
    args: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    duration_ms: float = 0.0,
    error: Optional[str] = None,
) -> Optional[str]:
    """
    Emit a syscall event using the current trace context (async version).
    For use in async handlers, code nodes, MCP adapters, etc.
    Writes through the unified add_syscall_event → SQLite + EventBus + SSE path.
    """
    import uuid
    import time as _time

    ctx = get_active_trace_context()
    if not ctx:
        return None

    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        store = rt.execution_store if rt and hasattr(rt, "execution_store") else None
        if not store:
            return None

        eid = str(uuid.uuid4())
        event = {
            "id": eid,
            "run_id": ctx.run_id,
            "span_id": f"{ctx.span_id}:{name}" if ctx.span_id else f"trace:{name}:{eid[:8]}",
            "parent_span_id": ctx.span_id or ctx.parent_span_id,
            "kind": kind,
            "name": name,
            "status": status,
            "start_time": _time.time(),
            "end_time": _time.time(),
            "duration_ms": duration_ms,
            "args": args or {},
            "result": result or {},
            "error": error,
            "created_at": _time.time(),
        }
        await store.add_syscall_event(event)
        return eid
    except Exception:
        return None


def emit_trace_event(
    kind: str,
    name: str,
    status: str = "completed",
    *,
    args: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    duration_ms: float = 0.0,
    error: Optional[str] = None,
) -> Optional[str]:
    """
    Emit a syscall event using the current trace context (sync wrapper).
    For use in sync code. Schedules via asyncio.create_task if loop is running.
    Prefer emit_trace_event_async() in async contexts.
    """
    import asyncio
    import uuid

    ctx = get_active_trace_context()
    if not ctx:
        return None

    eid = str(uuid.uuid4())
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_async_emit(ctx, kind, name, status, args, result, duration_ms, error, eid))
            return eid
    except Exception:
        pass
    return None


async def _async_emit(
    ctx: ActiveTraceContext,
    kind: str,
    name: str,
    status: str,
    args: Optional[Dict],
    result: Optional[Dict],
    duration_ms: float,
    error: Optional[str],
    eid: str,
) -> Optional[str]:
    """Internal: async event emission via the unified add_syscall_event path."""
    import time as _time

    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        store = rt.execution_store if rt and hasattr(rt, "execution_store") else None
        if not store:
            return None

        event = {
            "id": eid,
            "run_id": ctx.run_id,
            "span_id": f"{ctx.span_id}:{name}" if ctx.span_id else f"trace:{name}:{eid[:8]}",
            "parent_span_id": ctx.parent_span_id or ctx.span_id,
            "kind": kind,
            "name": name,
            "status": status,
            "start_time": _time.time(),
            "end_time": _time.time(),
            "duration_ms": duration_ms,
            "args": args or {},
            "result": result or {},
            "error": error,
            "created_at": _time.time(),
        }
        await store.add_syscall_event(event)
        return eid
    except Exception:
        return None
