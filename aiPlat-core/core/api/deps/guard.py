from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas_run import RunStatus
from core.security.rbac import check_permission as rbac_check_permission, should_enforce as rbac_should_enforce
from core.utils.ids import new_prefixed_id

from .actor import actor_from_http


async def rbac_guard(
    *,
    http_request: Request,
    payload: Optional[Dict[str, Any]],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Optional[JSONResponse]:
    """Return JSONResponse when denied, otherwise None.

    Uses the same semantics as core.server._rbac_guard but without importing server.
    """
    actor = actor_from_http(http_request, payload)
    decision = rbac_check_permission(actor_role=actor.get("actor_role"), action=action, resource_type=resource_type)
    if decision.allowed:
        return None

    # audit best-effort
    rt = get_kernel_runtime()
    store = getattr(rt, "execution_store", None) if rt else None
    if store:
        try:
            await store.add_audit_log(
                action=f"rbac_{action}",
                status="denied" if rbac_should_enforce() else "warn",
                tenant_id=str(actor.get("tenant_id") or "") or None,
                actor_id=str(actor.get("actor_id") or "") or None,
                actor_role=str(actor.get("actor_role") or "") or None,
                resource_type=str(resource_type),
                resource_id=str(resource_id) if resource_id else None,
                run_id=str(run_id) if run_id else None,
                request_id=http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id"),
                detail={"reason": decision.reason},
            )
        except Exception:
            pass

    if rbac_should_enforce():
        body = {
            "ok": False,
            "run_id": str(run_id or new_prefixed_id("run")),
            "trace_id": None,
            "status": RunStatus.failed.value,
            "legacy_status": "forbidden",
            "output": None,
            "error": {"code": "FORBIDDEN", "message": "forbidden", "detail": {"reason": decision.reason}},
            "error_code": "FORBIDDEN",
            "error_message": "forbidden",
        }
        return JSONResponse(status_code=403, content=body)
    return None
