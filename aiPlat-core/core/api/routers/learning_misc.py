from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, Annotated, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import actor_from_http
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _approval_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "approval_manager", None) if rt else None


# ==================== Learning artifacts ====================


@router.post("/learning/approvals/cleanup-rollback-approvals", response_model=Dict[str, Any])
async def api_cleanup_rollback_approvals(request: dict, rt: RuntimeDep = None):
    """HTTP wrapper for cleanup-rollback-approvals."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    approval_mgr = _approval_mgr(rt)
    if not approval_mgr:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    from core.learning.autorollback import cleanup_rollback_approvals

    return await cleanup_rollback_approvals(
        store=store,
        approval_manager=approval_mgr,
        now=(float((request or {}).get("now")) if (request or {}).get("now") is not None else None),
        dry_run=bool((request or {}).get("dry_run", False)),
        user_id=(request or {}).get("user_id"),
        candidate_id=(request or {}).get("candidate_id"),
        page_size=int((request or {}).get("page_size", 500) or 500),
    )
