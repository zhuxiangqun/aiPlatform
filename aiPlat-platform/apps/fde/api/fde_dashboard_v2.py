"""FDE Dashboard V2 — unified management overview with metrics, activity, alerts, governance health (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List
from apps.fde.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException

import time

router = APIRouter(tags=["fde-dashboard-v2"])


@router.get("/dashboard", response_model=FdeItemResponse)
async def fde_dashboard():
    """Unified dashboard: key metrics, recent activity, alerts, governance health.

    Single-request management overview combining data from multiple subsystems.
    """
    import time as _td

    from .fde import (
        _get_governance_live_status,
        _get_convergence_status,
        _get_pipeline_health,
        _get_quick_quality_score,
        _get_evolution_stats,
        _get_manual_stats,
    )

    t0 = _td.time()
    status = _get_governance_live_status()
    governance = _get_convergence_status()

    # Quick metrics
    metrics = {
        "total_diagnoses": status.get("delivery_session_count", 0),
        "active_domains": status.get("configured_domains", 0),
        "knowledge_atoms": status.get("knowledge_atom_count", 0),
        "enterprise_terms": status.get("enterprise_term_count", 0),
        "delivery_rate": status.get("delivery_rate", 0),
        "convergence_triggers": governance.get("applied_triggers", 0),
        "pipeline_health": _get_pipeline_health(),
        "quality_score": _get_quick_quality_score(status, governance),
        "self_evolution": _get_evolution_stats(),
        "manuals": _get_manual_stats(),
    }

    # Recent activity (last 5 sessions)
    recent = []
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        fd = GraphIndex.load("fde-delivery")
        for nid, node in sorted(
            list(fd._nodes.items()),
            key=lambda x: x[0], reverse=True
        ):
            if getattr(node, "class_name", "") == "DiagnosisSession":
                recent.append({"id": nid[:60], "company": node.entity_name[:60]})
                if len(recent) >= 5:
                    break
    except Exception:
        pass

    # Active alerts (error-level only, top 3)
    alerts = []
    try:
        alert_data = list(fd._nodes.items())
        for nid, node in alert_data:
            if getattr(node, "class_name", "") != "DiagnosisSession":
                continue
            nb = fd.get_neighbor_edges(nid, direction="outgoing")
            for neighbor_id, edge in nb:
                if edge.relation_name == "has_transition":
                    tn = fd.get_node(neighbor_id)
                    if tn and "blocked" in (tn.entity_name or "").lower():
                        alerts.append({
                            "session": node.entity_name[:50],
                            "type": "blocked_action",
                            "severity": "error",
                        })
                        break
            if len(alerts) >= 3:
                break
    except Exception:
        pass

    # Governance health
    gov_health = "excellent" if metrics["delivery_rate"] >= 60 and metrics["enterprise_terms"] >= 10 else (
        "good" if metrics["delivery_rate"] >= 30 else "growing"
    )

    return {
        "metrics": metrics,
        "recent_activity": recent,
        "active_alerts": alerts,
        "governance_health": gov_health,
        "quick_actions": [
            "POST /fde/ask — 追问已有诊断",
            "POST /fde/delivery/feedback — 更新交付状态",
            "GET /fde/governance — 查看治理能力矩阵",
            "GET /fde/alerts — 查看完整告警列表",
        ],
        "elapsed_ms": round((_td.time() - t0) * 1000),
    }
