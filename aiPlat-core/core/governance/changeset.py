from __future__ import annotations

from typing import Any, Dict, Optional


async def record_changeset(
    *,
    store: Any,
    name: str,
    target_type: str,
    target_id: str,
    status: str = "success",
    args: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    user_id: str = "admin",
    session_id: Optional[str] = None,
    approval_request_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """Record a governance 'changeset' event (best-effort).

    IMPORTANT: Do not store secrets; pass hashes/lengths instead.
    """
    try:
        if not store:
            return
        await store.add_syscall_event(
            {
                "trace_id": str(trace_id) if trace_id else None,
                "run_id": str(run_id) if run_id else None,
                "kind": "changeset",
                "name": str(name),
                "status": str(status or "success"),
                "args": args or {},
                "result": result or {},
                "error": str(error) if error else None,
                "target_type": str(target_type),
                "target_id": str(target_id),
                "user_id": str(user_id or "admin"),
                "session_id": str(session_id) if session_id else None,
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
            }
        )
    except Exception:
        return

