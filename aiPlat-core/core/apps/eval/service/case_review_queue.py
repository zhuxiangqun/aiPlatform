"""P1.1 Case Pack human_review queue (draft → in_review → reviewed|rejected).

No freeze. claim_eligible stays false. No accuracy_claim.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.apps.eval.service.case_pack_registry import (
    PackRegistryError,
    get_pack_version,
    load_registry,
    update_pack_version_meta,
)

VALID_DECISIONS = frozenset({"approve", "reject"})
_QUEUE_STATUSES = frozenset({"draft", "in_review"})


class CaseReviewError(ValueError):
    """Human review queue failure."""


def enqueue_pack_for_review(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    caller_workspace_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Move workspace pack draft → in_review."""
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CaseReviewError("workspace_id required")
    try:
        cur = get_pack_version(
            pack_id=pack_id,
            version=version,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CaseReviewError(str(e)) from e
    st = str(cur.get("status") or "").lower()
    if st == "in_review":
        return {
            "ok": True,
            "pack_id": pack_id,
            "version": version,
            "status": "in_review",
            "noop": True,
            "claim_eligible": False,
        }
    if st not in ("draft", "rejected"):
        raise CaseReviewError(
            f"enqueue requires status draft|rejected, got {st!r}"
        )
    if str(cur.get("kind") or "").lower() == "frozen":
        raise CaseReviewError("frozen packs cannot enter review queue")
    meta = update_pack_version_meta(
        pack_id=pack_id,
        version=version,
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        status="in_review",
        review={
            "status": "in_review",
            "notes": str(notes or ""),
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "ok": True,
        "pack_id": str(pack_id).strip(),
        "version": str(version).strip(),
        "status": "in_review",
        "registry": meta,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "in_review; not frozen; accuracy_claim closed",
    }


def list_review_queue(
    *,
    workspace_id: str,
    caller_workspace_id: str = "",
    statuses: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """List workspace packs awaiting or eligible for review."""
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CaseReviewError("workspace_id required")
    # ACL via load through get path: assert via update/get pattern
    from core.apps.eval.service.case_pack_registry import assert_pack_acl

    assert_pack_acl(
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        write=False,
    )
    want = {str(s).strip().lower() for s in (statuses or list(_QUEUE_STATUSES))}
    reg = load_registry(scope="workspace", workspace_id=wid)
    items: List[Dict[str, Any]] = []
    for pid, entry in (reg.get("packs") or {}).items():
        if not isinstance(entry, dict):
            continue
        for ver, meta in (entry.get("versions") or {}).items():
            if not isinstance(meta, dict):
                continue
            st = str(meta.get("status") or "").lower()
            if st not in want:
                continue
            items.append(
                {
                    "pack_id": pid,
                    "version": ver,
                    "status": st,
                    "kind": meta.get("kind"),
                    "claim_eligible": bool(meta.get("claim_eligible")),
                    "hash": meta.get("hash"),
                    "review": meta.get("review") or {},
                }
            )
    items.sort(key=lambda r: (r["pack_id"], r["version"]))
    return {
        "ok": True,
        "workspace_id": wid,
        "n": len(items),
        "items": items,
        "claim_eligible": False,
    }


def submit_review_decision(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    decision: str,
    reviewer: str = "",
    notes: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Approve → reviewed, reject → rejected. Never freezes or opens claim."""
    wid = str(workspace_id or "").strip()
    dec = str(decision or "").strip().lower()
    if dec not in VALID_DECISIONS:
        raise CaseReviewError(
            f"decision must be approve|reject, got {decision!r}"
        )
    try:
        cur = get_pack_version(
            pack_id=pack_id,
            version=version,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CaseReviewError(str(e)) from e
    st = str(cur.get("status") or "").lower()
    if st != "in_review":
        raise CaseReviewError(
            f"submit_review_decision requires status=in_review, got {st!r}"
        )
    if str(cur.get("kind") or "").lower() == "frozen":
        raise CaseReviewError("frozen packs cannot be decided here")
    new_status = "reviewed" if dec == "approve" else "rejected"
    meta = update_pack_version_meta(
        pack_id=pack_id,
        version=version,
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        status=new_status,
        review={
            "status": new_status,
            "decision": dec,
            "reviewer": str(reviewer or ""),
            "notes": str(notes or ""),
            "decided_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "ok": True,
        "pack_id": str(pack_id).strip(),
        "version": str(version).strip(),
        "decision": dec,
        "status": new_status,
        "registry": meta,
        "claim_eligible": False,
        "kind": meta.get("kind"),
        "frozen": False,
        "accuracy_claim": False,
        "honesty": "reviewed≠frozen; claim_eligible=false; accuracy_claim closed",
    }
