"""Human Gate / Canary / 回滚离线演练（Phase 1 / G1）。

仅走 Candidate.status 状态机；不写生产配置、不采生产流量。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.harness.evo_compute.status import advance_candidate_status


def run_human_gate_canary_rollback_drill(
    *,
    candidate_id: str,
    actor: str = "drill-operator",
    evidence_ref: str = "g1-drill",
) -> Dict[str, Any]:
    """演练：ranked → safety_passed → human_gate → approved → canary → rolled_back。

    Args:
        candidate_id: 候选 id。
        actor: 演练操作者。
        evidence_ref: 证据前缀。

    Returns:
        回执；``production_write`` 恒 false；不宣称 g1_complete。
    """
    cid = str(candidate_id or "").strip() or "drill-cand"
    act = str(actor or "drill-operator").strip()
    path: List[Tuple[str, str]] = [
        ("ranked", "safety_passed"),
        ("safety_passed", "human_gate"),
        ("human_gate", "approved"),
        ("approved", "canary"),
        ("canary", "rolled_back"),
    ]
    transitions = []
    status = "ranked"
    for fr, to in path:
        step = advance_candidate_status(
            candidate_id=cid,
            from_status=fr,
            to_status=to,
            actor=act,
            evidence_ref=f"{evidence_ref}:{fr}->{to}",
        )
        transitions.append(step)
        if not step.get("ok"):
            return {
                "ok": False,
                "candidate_id": cid,
                "error": step.get("error") or "transition_failed",
                "status": status,
                "transitions": transitions,
                "human_gate_ok": False,
                "canary_ok": False,
                "rollback_ok": False,
                "production_write": False,
                "g1_foundation": True,
                "g1_complete": False,
                "certified": False,
                "e2_claimed": False,
            }
        status = str(step.get("status") or to)

    return {
        "ok": True,
        "candidate_id": cid,
        "status": status,
        "transitions": transitions,
        "human_gate_ok": True,
        "canary_ok": True,
        "rollback_ok": status == "rolled_back",
        "production_write": False,
        "g1_foundation": True,
        "g1_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "status-machine drill only; not production canary",
    }
