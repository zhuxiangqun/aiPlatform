"""FDE Delivery — delivery feedback state transitions via GraphIndex (split from fde.py lines 2104-2233)."""
from __future__ import annotations

from typing import Any
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException

from pydantic import BaseModel as _PydanticBaseModel

router = APIRouter(tags=["fde-delivery"])


class FdeDeliveryFeedbackRequest(_PydanticBaseModel):
    session_id: str
    status: str = ""       # delivered | in_progress | completed | blocked | abandoned
    action_name: str = ""  # optional: target a specific DeliveryAction


@router.post("/delivery/feedback", response_model=FdeStatusResponse)
async def fde_delivery_feedback(req: FdeDeliveryFeedbackRequest):
    """Mark delivery status for a diagnosis session or its actions. (L: Action bridge)

    Creates StateTransition entities to track the full lifecycle.
    Returns updated session stats + transition timeline.
    """
    import time as _time_df

    sid = req.session_id.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")

    status = req.status.strip().lower()
    action_name = req.action_name.strip()

    try:
        from core.api.core_facade import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        session_node = fd.get_node(sid) or fd.find_by_name(sid)
        if not session_node:
            for nid, node in list(fd._nodes.items()):
                if sid in nid or sid in node.entity_name:
                    session_node = node
                    sid = nid
                    break
        if not session_node:
            raise HTTPException(status_code=404, detail=f"Session {sid} not found")

        ts = str(int(_time_df.time()))
        transitions = []

        if action_name:
            # Target a specific action
            neighbors = fd.get_neighbor_edges(sid, direction="outgoing")
            targeted = False
            for neighbor_id, edge in neighbors:
                if edge.relation_name == "has_action":
                    action_node = fd.get_node(neighbor_id)
                    if action_node and action_name.lower() in action_node.entity_name.lower():
                        targeted = True
                        # L: Create state transition entity
                        tid = f"trans_{sid}_{ts}_{neighbor_id[:8]}"
                        fd.add_entity(tid,
                            f"{action_node.entity_name[:60]} → {status}",
                            "StateTransition",
                            source_doc_id=sid)
                        fd.add_relation(neighbor_id, tid, "has_transition",
                                       relation_label="状态变更",
                                       confidence=1.0)
                        transitions.append({
                            "target": "action",
                            "entity": action_node.entity_name[:60],
                            "from_state": "previous",
                            "to_state": status,
                            "transition_id": tid,
                        })
            if not targeted:
                raise HTTPException(status_code=404,
                    detail=f"Action '{action_name}' not found in session {sid}")
        else:
            # Session-level status change
            tid = f"trans_{sid}_{ts}"
            fd.add_entity(tid,
                f"Session → {status}",
                "StateTransition",
                source_doc_id=sid)
            fd.add_relation(sid, tid, "has_transition",
                           relation_label="状态变更",
                           confidence=1.0)
            transitions.append({
                "target": "session",
                "entity": session_node.entity_name,
                "from_state": "previous",
                "to_state": status,
                "transition_id": tid,
            })

            # Cascade to all actions
            neighbors = fd.get_neighbor_edges(sid, direction="outgoing")
            for neighbor_id, edge in neighbors:
                if edge.relation_name == "has_action":
                    atid = f"trans_{sid}_{ts}_{neighbor_id[:8]}"
                    fd.add_entity(atid,
                        f"Action → {status} (session cascade)",
                        "StateTransition",
                        source_doc_id=sid)
                    fd.add_relation(neighbor_id, atid, "has_transition",
                                   relation_label="状态变更(级联)",
                                   confidence=0.9)

        # ── Compute updated stats ──
        total_sessions = sum(1 for _, n in fd._nodes.items()
                            if getattr(n, "class_name", "") == "DiagnosisSession")
        completed = sum(1 for _, n in fd._nodes.items()
                       if getattr(n, "class_name", "") == "DiagnosisSession"
                       and any(e.relation_name == "has_action" for _, e in
                              fd.get_neighbor_edges(getattr(n, "entity_id", "") or "", direction="outgoing")))

        # Count transitions for this session
        session_transitions = sum(1 for _, n in fd._nodes.items()
                                 if getattr(n, "class_name", "") == "StateTransition"
                                 and sid in getattr(n, "source_doc_id", ""))

        return {
            "session_id": sid,
            "status": status,
            "transitions": transitions,
            "total_transitions_for_session": session_transitions,
            "stats": {
                "total_sessions": total_sessions,
                "sessions_with_actions": completed,
                "delivery_rate": round(completed / total_sessions * 100) if total_sessions else 0,
            },
        }
    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delivery feedback failed: {str(e)[:300]}")
