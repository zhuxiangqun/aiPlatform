"""FDE Phase 4 — security preflight (4A) + evolve proposal gate (4B) APIs.

Proxies security dry-run via CoreFacade only — no direct security_* handler imports.
AI FDE half-step: approve / reject / apply / rollback + D6 metrics.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.fde.api.schemas import FdeItemResponse, FdeListResponse, FdeStatusResponse

router = APIRouter(tags=["fde-phase4"])


class SecurityPreflightRequest(BaseModel):
    force: bool = False
    max_paths: int = 20
    phase_c_enabled: bool = False
    actor: str = "fde_engineer"


class EvolveProposalRequest(BaseModel):
    keys: List[str] = Field(default_factory=list)
    proposed_changes: Dict[str, Any] = Field(default_factory=dict)
    actor: str = "agent"
    domain_id: str = ""
    touches_abox: bool = False
    touches_ontology: bool = False
    summary: str = ""


class EvolveReviewRequest(BaseModel):
    actor: str = "approver"
    reason: str = ""


@router.post("/security-preflight/run", response_model=FdeItemResponse)
async def run_security_preflight(req: SecurityPreflightRequest) -> Dict[str, Any]:
    """FDE 4A = security B/C. Default Phase B; Phase C only when phase_c_enabled=true."""
    try:
        from core.api.core_facade import (
            run_security_review_dry,
            save_fde_security_preflight_run,
        )

        dry = run_security_review_dry(
            force=bool(req.force),
            max_paths=int(req.max_paths or 20),
            phase_c_enabled=bool(req.phase_c_enabled),
        )
        if not isinstance(dry, dict):
            dry = {"status": "ok", "phase": "B", "result": dry}
        record = save_fde_security_preflight_run(
            dry_run=dry,
            actor=req.actor,
            phase_c_enabled=bool(req.phase_c_enabled),
            max_paths=int(req.max_paths or 20),
        )
        return {
            "label": "FDE 4A = security B/C",
            "run": record,
            "dry_run_phase": dry.get("phase"),
            "dry_run_status": dry.get("status"),
            "security_report": dry.get("security_report"),
            "security_critique": dry.get("security_critique"),
            "security_evidence": dry.get("security_evidence"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.get("/security-preflight/latest", response_model=FdeItemResponse)
async def latest_security_preflight() -> Dict[str, Any]:
    from core.api.core_facade import get_fde_security_preflight_latest

    latest = get_fde_security_preflight_latest()
    if not latest:
        return {"label": "FDE 4A = security B/C", "run": None}
    return {"label": "FDE 4A = security B/C", "run": latest}


@router.get("/security-preflight", response_model=FdeListResponse)
async def list_security_preflight(limit: int = 10) -> Dict[str, Any]:
    from core.api.core_facade import list_fde_security_preflight_runs

    items = list_fde_security_preflight_runs(limit=min(limit, 30))
    return {"items": items, "total": len(items)}


@router.post("/evolve-proposals/evaluate", response_model=FdeItemResponse)
async def evaluate_evolve(req: EvolveProposalRequest) -> Dict[str, Any]:
    """Phase 4B: evolve_proposal gate only — does not apply mutations."""
    from core.api.core_facade import evaluate_fde_evolve_proposal

    return evaluate_fde_evolve_proposal(
        keys=req.keys,
        proposed_changes=req.proposed_changes,
        actor=req.actor,
        domain_id=req.domain_id,
        touches_abox=req.touches_abox,
        touches_ontology=req.touches_ontology,
    )


@router.post("/evolve-proposals", response_model=FdeStatusResponse)
async def enqueue_evolve(req: EvolveProposalRequest) -> Dict[str, Any]:
    from core.api.core_facade import enqueue_fde_evolve_proposal

    result = enqueue_fde_evolve_proposal(
        keys=req.keys,
        proposed_changes=req.proposed_changes,
        actor=req.actor,
        domain_id=req.domain_id,
        touches_abox=req.touches_abox,
        touches_ontology=req.touches_ontology,
        summary=req.summary,
    )
    status = "ok" if result.get("queued") or result.get("status") == "auto_allow" else "rejected"
    return {"status": status, "message": result.get("status", ""), "data": result}


@router.get("/evolve-proposals", response_model=FdeListResponse)
async def list_evolve(limit: int = 20) -> Dict[str, Any]:
    from core.api.core_facade import list_fde_evolve_proposals

    items = list_fde_evolve_proposals(limit=min(limit, 50))
    return {"items": items, "total": len(items)}


@router.get("/evolve-proposals/metrics", response_model=FdeItemResponse)
async def evolve_metrics() -> Dict[str, Any]:
    from core.api.core_facade import get_fde_evolve_metrics

    return get_fde_evolve_metrics()


@router.get("/evolve-proposals/applied", response_model=FdeListResponse)
async def list_evolve_applied(limit: int = 20) -> Dict[str, Any]:
    from core.api.core_facade import list_fde_evolve_applied

    items = list_fde_evolve_applied(limit=min(limit, 50))
    return {"items": items, "total": len(items)}


@router.get("/evolve-proposals/applied-config", response_model=FdeItemResponse)
async def evolve_applied_config() -> Dict[str, Any]:
    from core.api.core_facade import get_fde_evolve_applied_config

    return {"config": get_fde_evolve_applied_config()}


@router.post("/evolve-proposals/tick-observations", response_model=FdeItemResponse)
async def tick_evolve_observations() -> Dict[str, Any]:
    """Promote observing → stable when observation window elapsed."""
    from core.api.core_facade import tick_fde_evolve_observations

    return tick_fde_evolve_observations()


class EvolveObserveRequest(BaseModel):
    actor: str = "system"
    metric_name: str = "quality_score"
    metric_value: float = 0.0
    baseline_value: Optional[float] = None


@router.post("/evolve-proposals/{proposal_id}/approve", response_model=FdeStatusResponse)
async def approve_evolve(proposal_id: str, req: EvolveReviewRequest) -> Dict[str, Any]:
    from core.api.core_facade import approve_fde_evolve_proposal

    try:
        rec = approve_fde_evolve_proposal(proposal_id, actor=req.actor)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"status": "ok", "message": "approved", "data": rec}


@router.post("/evolve-proposals/{proposal_id}/reject", response_model=FdeStatusResponse)
async def reject_evolve(proposal_id: str, req: EvolveReviewRequest) -> Dict[str, Any]:
    from core.api.core_facade import reject_fde_evolve_proposal

    try:
        rec = reject_fde_evolve_proposal(proposal_id, actor=req.actor, reason=req.reason)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"status": "ok", "message": "rejected", "data": rec}


@router.post("/evolve-proposals/{proposal_id}/apply", response_model=FdeStatusResponse)
async def apply_evolve(proposal_id: str, req: EvolveReviewRequest) -> Dict[str, Any]:
    """Controlled apply → observing window (whitelist config only)."""
    from core.api.core_facade import apply_fde_evolve_proposal

    try:
        rec = apply_fde_evolve_proposal(proposal_id, actor=req.actor)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"status": "ok", "message": "observing", "data": rec}


@router.post("/evolve-proposals/{proposal_id}/observe", response_model=FdeStatusResponse)
async def observe_evolve(proposal_id: str, req: EvolveObserveRequest) -> Dict[str, Any]:
    """Record observation sample; quality_score breach may auto-rollback."""
    from core.api.core_facade import record_fde_evolve_observation

    try:
        out = record_fde_evolve_observation(
            proposal_id,
            metric_name=req.metric_name,
            metric_value=req.metric_value,
            baseline_value=req.baseline_value,
            actor=req.actor,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    msg = "rolled_back" if isinstance(out, dict) and out.get("review_status") == "rolled_back" else "observed"
    return {"status": "ok", "message": msg, "data": out}


@router.post("/evolve-proposals/{proposal_id}/rollback", response_model=FdeStatusResponse)
async def rollback_evolve(proposal_id: str, req: EvolveReviewRequest) -> Dict[str, Any]:
    from core.api.core_facade import rollback_fde_evolve_proposal

    try:
        rec = rollback_fde_evolve_proposal(proposal_id, actor=req.actor)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"status": "ok", "message": "rolled_back", "data": rec}
