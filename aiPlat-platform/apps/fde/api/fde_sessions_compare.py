"""FDE Sessions Compare — side-by-side comparison of two diagnosis sessions (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

import json

router = APIRouter(tags=["fde-sessions-compare"])

# ── Evidence source labels ──
_EVIDENCE_SOURCE_LLM = "LLM推测"
_EVIDENCE_SOURCE_INDUSTRY = "行业普遍痛点"


@router.get("/sessions/compare", response_model=dict)
async def fde_compare_sessions(
    left: str = Query("", description="Left session ID"),
    right: str = Query("", description="Right session ID"),
):
    """Compare two diagnosis sessions side by side.

    Useful for: before/after analysis (same customer), cross-customer comparison
    (same industry), or solution effectiveness comparison.
    """
    if not left or not right:
        raise HTTPException(status_code=400, detail="Both left and right session IDs are required")

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        import json as _json_cmp

        fd = GraphIndex.load("fde-delivery")

        def _get_session_data(sid: str) -> dict:
            """Extract key session data for comparison."""
            node = fd.get_node(sid) or fd.find_by_name(sid)
            if not node:
                for nid, n in list(fd._nodes.items()):
                    if sid in nid or sid in n.entity_name:
                        node = n
                        sid = nid
                        break
            if not node:
                return {"error": f"Session {sid} not found", "session_id": sid}

            data = {"session_id": sid, "company": node.entity_name}
            neighbors = list(fd.get_neighbors(sid, direction="outgoing"))

            # Evidence map
            for nid, e in neighbors:
                if e.relation_name == "has_meta":
                    mn = fd.get_node(nid)
                    if mn:
                        try:
                            md = _json_cmp.loads(mn.entity_name)
                            data["evidence_map"] = md.get("evidence_map", [])
                            data["readiness_score"] = md.get("readiness_score", 0)
                            data["industry"] = md.get("industry", "")
                            data["knowledge_gaps"] = len(md.get("knowledge_gaps", []))
                        except Exception:
                            pass

            # Actions
            actions = 0
            for _, e in neighbors:
                if e.relation_name == "has_action":
                    actions += 1
            data["action_count"] = actions

            # Transitions
            transitions = sum(1 for _, e in neighbors if e.relation_name == "has_transition")
            data["transition_count"] = transitions

            # Evidence coverage
            em = data.get("evidence_map", [])
            if em:
                backed = sum(1 for x in em if x.get("source") and x["source"] not in ("", _EVIDENCE_SOURCE_LLM, _EVIDENCE_SOURCE_INDUSTRY))
                data["evidence_backed"] = backed
                data["evidence_total"] = len(em)
                data["coverage_rate"] = round(backed / max(len(em), 1) * 100)

            return data

        left_data = _get_session_data(left)
        right_data = _get_session_data(right)

        # Compute deltas
        deltas = {}
        for key in ["readiness_score", "action_count", "transition_count", "coverage_rate", "knowledge_gaps"]:
            lv = left_data.get(key, 0) or 0
            rv = right_data.get(key, 0) or 0
            if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                deltas[key] = rv - lv

        return {
            "left": left_data,
            "right": right_data,
            "deltas": deltas,
            "summary": (
                f"右侧会话较左侧：就绪度{'+' if deltas.get('readiness_score', 0) >= 0 else ''}"
                f"{deltas.get('readiness_score', 0)}，证据覆盖率"
                f"{'+' if deltas.get('coverage_rate', 0) >= 0 else ''}"
                f"{deltas.get('coverage_rate', 0)}%"
            ) if deltas else "无法计算差异",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session comparison failed: {str(e)[:300]}")
