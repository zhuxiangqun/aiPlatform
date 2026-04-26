from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


@router.get("/executions/{execution_id}/trace")
async def get_trace_by_execution(execution_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get trace (with spans) by execution_id (agent/skill)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    trace_id = await store.get_trace_id_by_execution_id(execution_id)
    if not trace_id:
        raise HTTPException(status_code=404, detail=f"Trace not found for execution {execution_id}")
    trace = await store.get_trace(trace_id, include_spans=True)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    trace["start_time"] = datetime.utcfromtimestamp(trace["start_time"]).isoformat() if trace.get("start_time") else None
    trace["end_time"] = datetime.utcfromtimestamp(trace["end_time"]).isoformat() if trace.get("end_time") else None
    return trace

