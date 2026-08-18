from __future__ import annotations

from typing import Dict, Annotated, Optional, Any

from fastapi import APIRouter, Depends, HTTPException

from core.api.core_facade import KernelRuntime  # P0-A2: 经 CoreFacade
from core.api.core_facade import get_kernel_runtime  # P0-A2: 经 CoreFacade

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


@router.get("/syscalls/events", response_model=Dict[str, Any])
async def list_syscall_events(
    limit: int = 100,
    offset: int = 0,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    kind: Optional[str] = None,
    name: Optional[str] = None,
    status: Optional[str] = None,
    error_contains: Optional[str] = None,
    error_code: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    approval_request_id: Optional[str] = None,
    span_id: Optional[str] = None,
    rt: RuntimeDep = None,
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_syscall_events(
        limit=limit,
        offset=offset,
        trace_id=trace_id,
        run_id=run_id,
        kind=kind,
        name=name,
        status=status,
        error_contains=error_contains,
        error_code=error_code,
        target_type=target_type,
        target_id=target_id,
        approval_request_id=approval_request_id,
        span_id=span_id,
    )


@router.get("/syscalls/stats", response_model=Dict[str, Any])
async def get_syscall_stats(
    window_hours: int = 24,
    top_n: int = 10,
    kind: Optional[str] = None,
    rt: RuntimeDep = None,
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.get_syscall_event_stats(window_hours=window_hours, top_n=top_n, kind=kind)

