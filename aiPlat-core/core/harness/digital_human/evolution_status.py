"""自进化状态聚合快照（管理端可见面）。

非目标：不宣称 E5；不替代各域原生审计库。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger("aiplat.digital_human.evolution_status")


def _timeline_from_proposals(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从提案台账推导时间线事件。"""
    events: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "")
        kind = str(row.get("kind") or "")
        title = str(row.get("title") or "")[:80]
        created = int(row.get("created_at") or 0)
        if created:
            events.append(
                {
                    "ts": created,
                    "event": "created",
                    "proposal_id": pid,
                    "kind": kind,
                    "title": title,
                    "status": "HUMAN_GATE",
                    "summary": str(row.get("summary") or "")[:160],
                }
            )
        decision = row.get("decision") if isinstance(row.get("decision"), dict) else None
        if decision:
            at = int(decision.get("at") or row.get("updated_at") or 0)
            dec = str(decision.get("decision") or "")
            events.append(
                {
                    "ts": at,
                    "event": dec or "decided",
                    "proposal_id": pid,
                    "kind": kind,
                    "title": title,
                    "status": str(row.get("status") or ""),
                    "actor": str(decision.get("actor") or ""),
                    "reason": str(decision.get("reason") or "")[:200],
                }
            )
        st = str(row.get("status") or "")
        if st == "APPLIED" and row.get("apply_result"):
            events.append(
                {
                    "ts": int(row.get("updated_at") or created or 0),
                    "event": "applied",
                    "proposal_id": pid,
                    "kind": kind,
                    "title": title,
                    "status": st,
                    "summary": str((row.get("apply_result") or {}).get("note") or "")[:160],
                }
            )
        if st == "ROLLED_BACK":
            events.append(
                {
                    "ts": int(row.get("updated_at") or 0),
                    "event": "rolled_back",
                    "proposal_id": pid,
                    "kind": kind,
                    "title": title,
                    "status": st,
                    "reason": str((decision or {}).get("reason") or "")[:200],
                }
            )
    events.sort(key=lambda e: int(e.get("ts") or 0), reverse=True)
    return events


def get_evolution_status_snapshot(*, limit: int = 50) -> Dict[str, Any]:
    """聚合五域目标 + 提案列表 + 时间线。

    Args:
        limit: 提案/时间线条数上限。

    Returns:
        goals / proposals / timeline；e5_claimed 恒 false。
    """
    from core.harness.digital_human.evolution_goals import measure_all_evolution_goals
    from core.harness.digital_human.evolution_proposals import (
        STATUS_APPLIED,
        STATUS_HUMAN_GATE,
        list_evolution_proposals,
        pending_human_gate_count,
    )

    lim = max(1, min(200, int(limit)))
    try:
        goals = measure_all_evolution_goals()
    except Exception as e:
        logger.debug("measure goals failed", exc_info=True)
        goals = {"ok": False, "reason": str(e), "goals": [], "e5_claimed": False}

    proposals = list_evolution_proposals(limit=lim)
    slim: List[Dict[str, Any]] = []
    for row in proposals:
        pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        slim.append(
            {
                "id": row.get("id"),
                "kind": row.get("kind"),
                "title": row.get("title"),
                "summary": row.get("summary"),
                "status": row.get("status"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "goal_id": pl.get("goal_id") or (row.get("goal_id")),
                "decision": row.get("decision"),
                "production_model_changed": False,
            }
        )

    pending = [p for p in slim if str(p.get("status") or "") == STATUS_HUMAN_GATE]
    applied = [p for p in slim if str(p.get("status") or "") == STATUS_APPLIED]
    timeline = _timeline_from_proposals(proposals)[:lim]

    return {
        "ok": True,
        "generated_at": int(time.time()),
        "goals": goals,
        "proposals": slim,
        "pending": pending,
        "applied": applied,
        "pending_count": pending_human_gate_count(),
        "timeline": timeline,
        "e5_claimed": False,
        "production_model_changed": False,
        "feeds_production_routing": False,
        "note": "status console; reject pending or rollback applied for wrong direction",
    }
