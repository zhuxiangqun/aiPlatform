u"""Governance Dashboard — 治理仪表盘后端聚合 (v2.8).

Aggregates all governance data sources into a single dashboard JSON.
"""
from __future__ import annotations

import logging
import os as _os
import sqlite3 as _sqlite3
import time as _time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("governance_dashboard")


def aggregate_dashboard() -> Dict[str, Any]:
    u"""Aggregate all governance metrics into dashboard data."""
    data = {
        "overall_health": 0,
        "health_level": "unknown",
        "mechanism_status": {},
        "pending_approvals": 0,
        "mapping_coverage": [],
        "cycle_history": [],
        "audit_summary": {},
    }

    # 1. Domain maturity aggregate as health indicator
    try:
        from core.harness.knowledge.domain_maturity import compare_domains
        domains = compare_domains()
        if domains:
            scores = [d["maturity_score"] for d in domains if d.get("maturity_score", 0) > 0]
            if scores:
                data["overall_health"] = round(sum(scores) / max(len(scores), 1), 1)
                data["health_level"] = (
                    "good" if data["overall_health"] >= 80
                    else "warning" if data["overall_health"] >= 60
                    else "critical"
                )
            else:
                # No measured maturity → unavailable (not fake 0/critical)
                data["overall_health"] = None
                data["health_level"] = "unknown"
        else:
            data["overall_health"] = None
            data["health_level"] = "unknown"
    except Exception:
        logging.getLogger(__name__).debug('aggregate_dashboard failed', exc_info=True)

    # 2. Mechanism status
    try:
        from core.harness.knowledge.mapping_validator import validate_all_sources
        mapping_results = validate_all_sources()
        data["mechanism_status"]["mapping_validation"] = {
            "status": "good" if all(r.status == "good" for r in mapping_results) else "warning",
            "detail": f"{len(mapping_results)} sources validated",
        }
    except Exception:
        data["mechanism_status"]["mapping_validation"] = {"status": "unknown"}

    try:
        from core.harness.infrastructure.gates.ontology_approval import list_pending, get_history
        pending = list_pending()
        history = get_history(limit=20)
        data["pending_approvals"] = len(pending)
        data["mechanism_status"]["change_approval"] = {
            "status": "good" if len(pending) == 0 else "warning",
            "detail": f"{len(pending)} pending, {len(history)} total",
        }
    except Exception:
        data["mechanism_status"]["change_approval"] = {"status": "unknown"}
        data["pending_approvals"] = 0

    # Mechanisms without a live probe stay unknown — never paint fake green.
    for _mech, _detail in (
        ("version_management", "not measured (no live probe)"),
        ("asset_publishing", "not measured (no live probe)"),
        ("agent_audit", "not measured (no live probe)"),
        ("quality_evaluation", "not measured (use gold / org-harness KPIs)"),
        ("feedback_loop", "not measured (no live probe)"),
    ):
        data["mechanism_status"][_mech] = {"status": "unknown", "detail": _detail}

    # 3. Mapping coverage per domain
    try:
        from core.harness.knowledge.mapping_validator import validate_all_sources
        results = validate_all_sources()
        data["mapping_coverage"] = [
            {"domain_id": r.domain_id, "source_id": r.source_id,
             "coverage": r.coverage_pct, "status": r.status}
            for r in results
        ]
    except Exception:
        logging.getLogger(__name__).debug('code failed', exc_info=True)

    # 4. Governance cycle history
    try:
        from core.harness.knowledge.governance_pipeline import get_cycle_history
        data["cycle_history"] = get_cycle_history(limit=10)
    except Exception:
        logging.getLogger(__name__).debug('code failed', exc_info=True)

    # 5. Audit summary
    try:
        db = _os.path.expanduser("~/.aiplat/usage_metrics.db")
        if _os.path.exists(db):
            conn = _sqlite3.connect(db, timeout=5.0)
            today_start = _time.time() - (_time.time() % 86400)
            events = conn.execute(
                "SELECT COUNT(*) FROM usage_events WHERE timestamp >= ?", (today_start,),
            ).fetchone()
            denied = conn.execute(
                "SELECT COUNT(*) FROM usage_events WHERE timestamp >= ? AND status = 'denied'",
                (today_start,),
            ).fetchone()
            conn.close()
            data["audit_summary"] = {
                "total_events_today": events[0] if events else 0,
                "denied_calls": denied[0] if denied else 0,
            }
    except Exception:
        logging.getLogger(__name__).debug('code failed', exc_info=True)

    return data
