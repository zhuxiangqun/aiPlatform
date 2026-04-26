from __future__ import annotations

from typing import Any, Dict, Optional


async def audit_event(
    *,
    store: Any,
    kind: str,
    name: str,
    status: str,
    args: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Best-effort append to ExecutionStore syscall_events for auditability."""
    try:
        if not store:
            return
        await store.add_syscall_event(
            {
                "kind": kind,
                "name": name,
                "status": status,
                "args": args or {},
                "result": result or {},
                "error": error,
            }
        )
    except Exception:
        return

