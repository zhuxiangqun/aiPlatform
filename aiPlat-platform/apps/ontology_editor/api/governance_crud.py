u"""Governance API — 治理管线 + 审批 + 映射验证 + 仪表盘 (v2.8)."""
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/governance", tags=["governance"])


# ── Dashboard ──

@router.get("/dashboard", response_model=Dict[str, Any])
async def governance_dashboard():
    u"""Aggregated governance dashboard data."""
    try:
        from core.harness.knowledge.governance_dashboard import aggregate_dashboard
        return aggregate_dashboard()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/audit-log", response_model=Dict[str, Any])
async def audit_log(days: int = Query(7), domain: str = Query("")):
    u"""Governance audit log."""
    try:
        import sqlite3, os, time
        db = os.path.expanduser("~/.aiplat/usage_metrics.db")
        if not os.path.exists(db):
            return {"events": [], "total": 0}
        cutoff = time.time() - days * 86400
        conn = sqlite3.connect(db, timeout=5.0)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM usage_events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 100"
        params = [cutoff]
        if domain:
            query = "SELECT * FROM usage_events WHERE timestamp >= ? AND domain_id = ? ORDER BY timestamp DESC LIMIT 100"
            params.append(domain)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return {"events": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/mapping-coverage", response_model=Dict[str, Any])
async def mapping_coverage_report():
    u"""Data→semantic mapping coverage report (markdown)."""
    try:
        from core.harness.knowledge.mapping_validator import generate_mapping_report
        report = generate_mapping_report()
        return {"format": "markdown", "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Governance Pipeline ──

@router.post("/run-cycle", response_model=Dict[str, Any])
async def run_cycle(data: Dict[str, Any]):
    u"""Run 6-step governance cycle for a domain."""
    try:
        domain_id = data.get("domain_id", "")
        if not domain_id:
            raise HTTPException(status_code=400, detail="domain_id required")
        from core.harness.knowledge.governance_pipeline import run_cycle as _run
        steps = data.get("steps")
        auto_publish = data.get("auto_publish", False)
        result = await _run(domain_id, steps=steps, auto_publish=auto_publish)
        return {
            "cycle_id": result.cycle_id, "domain_id": result.domain_id,
            "overall_health": result.overall_health, "health_level": result.health_level,
            "recommendations": result.recommendations,
            "step_results": [{"step_name": s.step_name, "status": s.status,
                               "metrics": s.metrics, "warnings": s.warnings}
                              for s in result.step_results],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-all", response_model=Dict[str, Any])
async def run_all_cycles():
    u"""Run governance cycle for all domains."""
    try:
        from core.harness.knowledge.governance_pipeline import run_all_domains
        results = await run_all_domains()
        return {
            "cycles": [{"domain_id": r.domain_id, "health": r.overall_health,
                         "level": r.health_level} for r in results],
            "total": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cycle-history", response_model=Dict[str, Any])
async def cycle_history(domain_id: str = Query(""), limit: int = Query(10)):
    u"""Governance cycle history."""
    try:
        from core.harness.knowledge.governance_pipeline import get_cycle_history
        history = get_cycle_history(domain_id, limit)
        return {"cycles": history, "total": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Change Approval ──

@router.get("/change-requests/pending", response_model=Dict[str, Any])
async def pending_requests(domain_id: str = Query("")):
    u"""List pending change requests."""
    try:
        from core.harness.infrastructure.gates.ontology_approval import list_pending
        pending = list_pending(domain_id)
        return {"requests": pending, "total": len(pending)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/change-requests/{request_id}/approve", response_model=Dict[str, Any])
async def approve_request(request_id: str, data: Dict[str, Any]):
    u"""Approve a change request."""
    try:
        from core.harness.infrastructure.gates.ontology_approval import approve
        approved_by = data.get("approved_by", "governance_admin")
        comment = data.get("comment", "")
        return approve(request_id, approved_by, comment)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/change-requests/{request_id}/reject", response_model=Dict[str, Any])
async def reject_request(request_id: str, data: Dict[str, Any]):
    u"""Reject a change request."""
    try:
        from core.harness.infrastructure.gates.ontology_approval import reject
        rejected_by = data.get("rejected_by", "governance_admin")
        reason = data.get("reason", "")
        return reject(request_id, rejected_by, reason)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/change-requests/history", response_model=Dict[str, Any])
async def approval_history(domain_id: str = Query(""), limit: int = Query(50)):
    u"""Approval history."""
    try:
        from core.harness.infrastructure.gates.ontology_approval import get_history
        history = get_history(domain_id, limit)
        return {"history": history, "total": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Mapping Validation ──

@router.post("/validate-mappings/{domain_id}", response_model=Dict[str, Any])
async def validate_mappings(domain_id: str):
    u"""Validate all data source mappings for a domain."""
    try:
        from core.harness.knowledge.mapping_validator import validate_all_sources
        results = validate_all_sources(domain_id)
        return {
            "domain_id": domain_id,
            "results": [{"source_id": r.source_id, "coverage_pct": r.coverage_pct,
                          "status": r.status, "issues": len(r.issues)} for r in results],
            "total": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mapping-report/{domain_id}", response_model=Dict[str, Any])
async def mapping_report(domain_id: str):
    u"""Mapping coverage markdown report."""
    try:
        from core.harness.knowledge.mapping_validator import generate_mapping_report
        report = generate_mapping_report([domain_id])
        return {"format": "markdown", "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
