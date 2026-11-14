"""audit：模块接口。"""

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
    """Best-effort append to ExecutionStore syscall_events for auditability.

    Args:
        store: store 参数。
        kind: kind 参数。
        name: name 参数。
        status: status 参数。
        args: args 参数。
        result: result 参数。
        error: error 参数。
    """
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

