"""
Platform execution-snapshot routes — self-service checkpoint recovery.

P1-2: exposes the on-disk pipeline execution snapshots (Hermes Layer 1
checkpoint) so operators can list, inspect, compare and restore historical
execution state. All access is mediated through CoreFacade per the layer
contract (platform → core via facade only).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import rbac_guard
from core.api import core_facade

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/execution/snapshots", tags=["execution-snapshots"])


@router.get("/{session_id}", response_model=Dict[str, Any])
async def list_snapshots(session_id: str, http_request: Request):
    """List all execution snapshots for a session (newest first)."""
    deny = await rbac_guard(
        http_request=http_request, payload=None,
        action="snapshot_list", resource_type="execution_snapshot", resource_id=str(session_id),
    )
    if deny:
        return deny
    items = core_facade.list_execution_snapshots(str(session_id))
    return {"session_id": str(session_id), "count": len(items), "items": items}


@router.get("/{session_id}/{snapshot_id}", response_model=Dict[str, Any])
async def get_snapshot(session_id: str, snapshot_id: str, http_request: Request):
    """Fetch a single snapshot header + full state (recovery payload)."""
    deny = await rbac_guard(
        http_request=http_request, payload=None,
        action="snapshot_read", resource_type="execution_snapshot", resource_id=str(snapshot_id),
    )
    if deny:
        return deny
    snap = core_facade.get_execution_snapshot(str(snapshot_id), str(session_id))
    if snap is None:
        raise HTTPException(status_code=404, detail="execution_snapshot_not_found")
    return snap


@router.get("/{session_id}/compare/{snapshot_a}/{snapshot_b}", response_model=Dict[str, Any])
async def compare_snapshots(session_id: str, snapshot_a: str, snapshot_b: str, http_request: Request):
    """Diff two snapshots (before/after strategy effect)."""
    deny = await rbac_guard(
        http_request=http_request, payload=None,
        action="snapshot_compare", resource_type="execution_snapshot", resource_id=str(session_id),
    )
    if deny:
        return deny
    return core_facade.compare_execution_snapshots(str(snapshot_a), str(snapshot_b), str(session_id))


@router.post("/{session_id}/{snapshot_id}/restore", response_model=Dict[str, Any])
async def restore_snapshot(session_id: str, snapshot_id: str, http_request: Request):
    """Restore (retrieve) the recoverable full state captured at checkpoint time.

    Returns the historical pipeline state so the caller can resume/inspect from it.
    """
    deny = await rbac_guard(
        http_request=http_request, payload=None,
        action="snapshot_restore", resource_type="execution_snapshot", resource_id=str(snapshot_id),
    )
    if deny:
        return deny
    payload = core_facade.restore_execution_snapshot(str(snapshot_id), str(session_id))
    if payload is None:
        raise HTTPException(status_code=404, detail="execution_snapshot_or_state_not_found")
    return payload


# ── File checkpoints — filesystem-level physical safety net (Hermes Layer 1) ──

file_router = APIRouter(prefix="/platform/execution/file-checkpoints", tags=["file-checkpoints"])


@file_router.get("", response_model=Dict[str, Any])
async def list_file_checkpoints(http_request: Request, session_id: str = "", path: str = ""):
    """List file checkpoints (content captured before write/edit overwrites)."""
    deny = await rbac_guard(
        http_request=http_request, payload=None,
        action="file_checkpoint_list", resource_type="file_checkpoint", resource_id=str(session_id or "default"),
    )
    if deny:
        return deny
    items = core_facade.list_file_checkpoints(session_id=str(session_id), path=str(path))
    return {"session_id": str(session_id or "default"), "count": len(items), "items": items}


@file_router.get("/{checkpoint_id}", response_model=Dict[str, Any])
async def get_file_checkpoint(checkpoint_id: str, http_request: Request, session_id: str = ""):
    """Fetch a file checkpoint header + stored content."""
    deny = await rbac_guard(
        http_request=http_request, payload=None,
        action="file_checkpoint_read", resource_type="file_checkpoint", resource_id=str(checkpoint_id),
    )
    if deny:
        return deny
    cp = core_facade.get_file_checkpoint(str(checkpoint_id), str(session_id))
    if cp is None:
        raise HTTPException(status_code=404, detail="file_checkpoint_not_found")
    return cp


@file_router.post("/{checkpoint_id}/restore", response_model=Dict[str, Any])
async def restore_file_checkpoint(checkpoint_id: str, http_request: Request, session_id: str = ""):
    """Restore a file to the content captured at checkpoint time (writes it back to disk)."""
    deny = await rbac_guard(
        http_request=http_request, payload=None,
        action="file_checkpoint_restore", resource_type="file_checkpoint", resource_id=str(checkpoint_id),
    )
    if deny:
        return deny
    result = core_facade.restore_file_checkpoint(str(checkpoint_id), str(session_id))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "file_checkpoint_restore_failed"))
    return result

