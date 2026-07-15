"""
Proposal Workflow API (P2: branch/merge semantics).
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["wiki-proposals"])


@router.get("/proposals", response_model=Dict[str, Any])
async def list_proposals(status: str = "", limit: int = 50):
    """List proposals with optional status filter."""
    from core.harness.learning.proposal_store import get_proposal_store
    store = get_proposal_store()
    items = store.list(status=status or None, limit=limit)
    return {"items": items, "stats": store.get_stats()}


@router.post("/proposals/{proposal_id}/submit", response_model=Dict[str, Any])
async def submit_proposal(proposal_id: str):
    """Submit a draft for review (draft -> pending_approval)."""
    from core.harness.learning.proposal_store import get_proposal_store
    store = get_proposal_store()
    if store.submit(proposal_id):
        return {"proposal_id": proposal_id, "status": "pending_approval"}
    raise HTTPException(status_code=404, detail="Not found or already submitted")


@router.post("/proposals/{proposal_id}/approve", response_model=Dict[str, Any])
async def approve_proposal(proposal_id: str, approved_by: str = "admin"):
    """Approve -> auto-merge."""
    from core.harness.learning.proposal_store import get_proposal_store
    store = get_proposal_store()
    if store.approve(proposal_id, approved_by):
        return {"proposal_id": proposal_id, "status": "merged"}
    raise HTTPException(status_code=404, detail="Not found or not pending_approval")


@router.post("/proposals/{proposal_id}/reject", response_model=Dict[str, Any])
async def reject_proposal(proposal_id: str, reason: str = ""):
    """Reject a proposal."""
    from core.harness.learning.proposal_store import get_proposal_store
    store = get_proposal_store()
    if store.reject(proposal_id, reason):
        return {"proposal_id": proposal_id, "status": "rejected"}
    raise HTTPException(status_code=404, detail="Not found")
