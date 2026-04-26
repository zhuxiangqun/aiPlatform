from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


def _job_scheduler(rt: RuntimeDep):
    return getattr(rt, "job_scheduler", None) if rt else None


def _approval_manager(rt: RuntimeDep):
    return getattr(rt, "approval_manager", None) if rt else None


@router.get("/health")
async def health_check(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Health check endpoint"""
    out: Dict[str, Any] = {"status": "healthy"}
    checks: Dict[str, Any] = {}
    store = _store(rt)

    # DB
    try:
        if store:
            v = await store.get_schema_version()
            checks["db"] = {"ok": True, "schema_version": v}
        else:
            checks["db"] = {"ok": False, "error": "ExecutionStore not initialized"}
            out["status"] = "degraded"
    except Exception as e:
        checks["db"] = {"ok": False, "error": str(e)}
        out["status"] = "degraded"

    # JobScheduler
    try:
        checks["job_scheduler"] = {"ok": bool(_job_scheduler(rt) is not None)}
    except Exception:
        checks["job_scheduler"] = {"ok": False}
        out["status"] = "degraded"

    # MCP runtime
    try:
        from core.mcp.runtime_sync import get_mcp_runtime

        checks["mcp_runtime"] = {"ok": bool(get_mcp_runtime() is not None)}
    except Exception:
        checks["mcp_runtime"] = {"ok": False}

    # Approval manager
    try:
        checks["approval_manager"] = {"ok": bool(_approval_manager(rt) is not None)}
    except Exception:
        checks["approval_manager"] = {"ok": False}
        out["status"] = "degraded"

    # DLQ depth (best-effort)
    try:
        if store:
            j = await store.list_job_delivery_dlq(status="pending", job_id=None, limit=1, offset=0)
            g = await store.list_connector_delivery_dlq(status="pending", limit=1, offset=0)
            checks["dlq"] = {"ok": True, "jobs_pending": int(j.get("total") or 0), "gateway_pending": int(g.get("total") or 0)}
    except Exception as e:
        checks["dlq"] = {"ok": False, "error": str(e)}
        out["status"] = "degraded"

    out["checks"] = checks
    return out


@router.get("/healthz")
async def healthz(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """K8s style health check (alias)."""
    return await health_check(rt)

