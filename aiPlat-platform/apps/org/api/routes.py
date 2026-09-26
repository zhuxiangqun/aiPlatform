"""Org L5 platform API — goals / runs / HITL resume / weekly KPI."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/org", tags=["org-l5"])


@router.get("/goals")
async def org_goals(domain_id: str = Query("")):
    try:
        from core.api.core_facade import org_list_goals

        return org_list_goals(domain_id or "")
    except Exception as e:
        logger.error("org_goals failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/goals/{goal_id}/status")
async def org_goal_status(goal_id: str, body: Dict[str, Any]):
    status = str(body.get("status") or "").strip()
    try:
        from core.api.core_facade import org_set_goal_status

        out = org_set_goal_status(goal_id, status)
        if out.get("status") in ("not_found", "invalid_status"):
            raise HTTPException(status_code=400, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_goal_status failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/goals/{goal_id}/runs")
async def org_goal_run(goal_id: str, request: Request, body: Dict[str, Any] = None):
    body = body or {}
    try:
        from core.api.core_facade import org_authorize_console_run, org_run_goal

        gid = "" if goal_id == "_" else goal_id
        auth = org_authorize_console_run(
            role=request.headers.get("x-aiplat-role") or "",
            domain_id=str(body.get("domain_id") or "it-ops"),
            goal_id=gid,
            post_id=str(body.get("post_id") or ""),
        )
        if not auth.get("ok"):
            raise HTTPException(status_code=403, detail=auth)
        out = org_run_goal(
            gid,
            domain_id=str(body.get("domain_id") or auth.get("domain_id") or "it-ops"),
            dry_actions=bool(body.get("dry_actions", True)),
            week_label=str(body.get("week_label") or ""),
        )
        if out.get("reason") == "edge_auto_apply_forbidden":
            raise HTTPException(status_code=409, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_goal_run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/runs")
async def org_runs(goal_id: str = Query(""), limit: int = Query(20, ge=1, le=100)):
    try:
        from core.api.core_facade import org_list_runs

        return org_list_runs(goal_id, limit=limit)
    except Exception as e:
        logger.error("org_runs failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/runs/{run_id}")
async def org_run_get(run_id: str):
    try:
        from core.api.core_facade import org_get_run

        out = org_get_run(run_id)
        if out.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_run_get failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/traces/{trace_id}")
async def org_trace_replay(trace_id: str, domain_id: str = Query("it-ops")):
    """V1: exact trace_id replay. Read-only."""
    try:
        from core.api.core_facade import org_replay_trace

        out = org_replay_trace(trace_id, domain_id=domain_id)
        if out.get("status") == "invalid":
            raise HTTPException(status_code=400, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_trace_replay failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/runs/{run_id}/resume")
async def org_run_resume(run_id: str, body: Dict[str, Any] = None):
    body = body or {}
    try:
        from core.api.core_facade import org_resume_run

        out = org_resume_run(
            run_id,
            approve=bool(body.get("approve", True)),
            resolution=str(body.get("resolution") or ""),
        )
        if out.get("status") in ("not_found", "not_waiting"):
            raise HTTPException(status_code=400, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_run_resume failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/goals/{goal_id}/weekly")
async def org_goal_weekly(
    goal_id: str,
    domain_id: str = Query("it-ops"),
    week: str = Query(""),
):
    try:
        from core.api.core_facade import org_weekly_kpi

        return org_weekly_kpi(domain_id or "it-ops", goal_id, week=week or "")
    except Exception as e:
        logger.error("org_goal_weekly failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/memory")
async def org_memory_list(domain_id: str = Query(""), limit: int = Query(50, ge=1, le=200)):
    try:
        from core.api.core_facade import org_list_memory

        return org_list_memory(domain_id or "", limit=limit)
    except Exception as e:
        logger.error("org_memory_list failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/memory/search")
async def org_memory_search(
    q: str = Query(""),
    domain_id: str = Query(""),
    limit: int = Query(20, ge=1, le=50),
):
    try:
        from core.api.core_facade import org_search_memory

        return org_search_memory(q, domain_id=domain_id or "", limit=limit)
    except Exception as e:
        logger.error("org_memory_search failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/fleet/gate")
async def org_fleet_gate_api(
    goal_id: str = Query(""),
    domain_id: str = Query("it-ops"),
    project_id: str = Query(""),
):
    try:
        from core.api.core_facade import org_fleet_gate

        return org_fleet_gate(goal_id, domain_id=domain_id or "it-ops", project_id=project_id or "")
    except Exception as e:
        logger.error("org_fleet_gate failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/goals/{goal_id}/fleet")
async def org_goal_fleet(goal_id: str, body: Dict[str, Any] = None):
    body = body or {}
    try:
        from core.api.core_facade import org_set_allow_fleet

        out = org_set_allow_fleet(goal_id, bool(body.get("allow", False)))
        if out.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_goal_fleet failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/rehearsals")
async def org_rehearsals_route(limit: int = Query(5, ge=1, le=20)):
    """List sandbox rehearsal logs. Does not start a fleet."""
    try:
        from core.api.core_facade import org_sandbox_rehearsals

        return org_sandbox_rehearsals(limit=limit)
    except Exception as e:
        logger.error("org_rehearsals failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/rehearsals")
async def org_rehearsal_start_route(request: Request, body: Dict[str, Any]):
    """Record a sandbox handoff. Does not flip allow_fleet."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_sandbox_rehearsal_start

        out = await org_sandbox_rehearsal_start(
            role=role,
            domain_id=str(body.get("domain_id") or ""),
            roles=list(body.get("roles") or []),
        )
        if not out.get("ok"):
            code = 403 if out.get("reason") in ("identity_missing", "rehearsal_forbidden") else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_rehearsal_start failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/rehearsals/conflict-probe")
async def org_conflict_probe_route(
    domain_id: str = Query("it-ops"),
    resource_id: str = Query("shared_interface"),
):
    """Sandbox concurrent lock probe. Second holder denied. No live write."""
    try:
        from core.api.core_facade import org_sandbox_conflict_probe

        return await org_sandbox_conflict_probe(
            domain_id=domain_id or "it-ops",
            resource_id=resource_id or "shared_interface",
        )
    except Exception as e:
        logger.error("org_conflict_probe failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/health/joint")
async def org_joint_health_route(domain_id: str = Query("it-ops")):
    """Read-only joint health. Does not write YAML or start a fleet."""
    try:
        from core.api.core_facade import org_joint_health

        return org_joint_health(domain_id or "it-ops")
    except Exception as e:
        logger.error("org_joint_health failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/field-ops/checklist")
async def org_field_checklist(domain_id: str = Query("it-ops")):
    try:
        from core.api.core_facade import org_field_ops_checklist

        return org_field_ops_checklist(domain_id or "it-ops")
    except Exception as e:
        logger.error("org_field_checklist failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/signoff")
async def org_customer_signoff(domain_id: str = Query("it-ops")):
    """V3: read-only customer signoff layer. No claim button."""
    try:
        from core.api.core_facade import org_customer_signoff as _view

        view = _view(domain_id or "it-ops")
        view["m4_claim_allowed"] = False
        view["signoff_button"] = False
        return view
    except Exception as e:
        logger.error("org_customer_signoff failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/signoff/prep")
async def org_signoff_prep_route(
    domain_id: str = Query("it-ops"),
    goal_id: str = Query("goal-it-ops-alert-sla"),
    format: str = Query("json"),
):
    """Read-only prep score for customer review. Not a signature."""
    try:
        from core.api.core_facade import org_signoff_prep

        out = org_signoff_prep(
            domain_id or "it-ops",
            goal_id or "goal-it-ops-alert-sla",
            as_markdown=(str(format or "").lower() == "markdown"),
        )
        out["m4_claim_allowed"] = False
        out["signoff_button"] = False
        return out
    except Exception as e:
        logger.error("org_signoff_prep failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/signoff/evidence-pack")
async def org_signoff_evidence_pack(
    request: Request,
    domain_id: str = Query("it-ops"),
    goal_id: str = Query("goal-it-ops-alert-sla"),
    week: str = Query(""),
    max_traces: int = Query(5),
    sandbox_mode: bool = Query(False),
    format: str = Query("json"),
):
    """H2: customer-safe evidence pack. Read-only. Not a signature."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_evidence_pack

        out = org_evidence_pack(
            role=role,
            domain_id=domain_id or "it-ops",
            goal_id=goal_id or "goal-it-ops-alert-sla",
            week=week or "",
            max_traces=min(5, max(1, int(max_traces or 5))),
            sandbox_mode=bool(sandbox_mode),
            as_markdown=(str(format or "").lower() == "markdown"),
        )
        out["m4_claim_allowed"] = False
        out["signoff_button"] = False
        if not out.get("ok"):
            code = 403 if out.get("reason") == "identity_missing" else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_signoff_evidence_pack failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/value/translation")
async def org_value_translation_route(
    domain_id: str = Query("it-ops"),
    goal_id: str = Query("goal-it-ops-alert-sla"),
    week: str = Query(""),
    tenant_id: str = Query(""),
):
    """H3: audit-friendly value translation. Read-only. Not a signature."""
    try:
        from core.api.core_facade import org_value_translation

        out = org_value_translation(
            domain_id=domain_id or "it-ops",
            goal_id=goal_id or "goal-it-ops-alert-sla",
            week=week or "",
            tenant_id=tenant_id or "",
        )
        out["m4_claim_allowed"] = False
        out["signoff_button"] = False
        return out
    except Exception as e:
        logger.error("org_value_translation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/value/roi-preview")
async def org_value_roi_preview_route(
    domain_id: str = Query("it-ops"),
    goal_id: str = Query("goal-it-ops-alert-sla"),
    week: str = Query(""),
    trial_minutes_per_incident: float = Query(...),
    trial_mtta_seconds: float = Query(...),
):
    """What-if ROI. Read-only. Never writes baseline. Not a signature."""
    try:
        from core.api.core_facade import org_value_roi_preview

        out = org_value_roi_preview(
            domain_id=domain_id or "it-ops",
            goal_id=goal_id or "goal-it-ops-alert-sla",
            week=week or "",
            trial_minutes_per_incident=float(trial_minutes_per_incident),
            trial_mtta_seconds=float(trial_mtta_seconds),
        )
        out["m4_claim_allowed"] = False
        out["signoff_button"] = False
        out["simulation"] = True
        if not out.get("ok"):
            raise HTTPException(status_code=400, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_value_roi_preview failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/value/baseline")
async def org_value_baseline_get_route(
    request: Request,
    tenant_id: str = Query("default"),
):
    """S2: read tenant value baseline."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_value_baseline_get

        out = org_value_baseline_get(role=role, tenant_id=tenant_id or "default")
        if not out.get("ok"):
            code = 403 if out.get("reason") == "identity_missing" else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_value_baseline_get failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.put("/value/baseline")
async def org_value_baseline_put_route(request: Request, body: Dict[str, Any]):
    """S2: write tenant value baseline. Not a signature."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_value_baseline_put

        out = org_value_baseline_put(
            role=role,
            tenant_id=str(body.get("tenant_id") or "default"),
            baseline_minutes_per_incident=float(body.get("baseline_minutes_per_incident") or 0),
            baseline_mtta_seconds=float(body.get("baseline_mtta_seconds") or 0),
        )
        if not out.get("ok"):
            code = 403 if out.get("reason") in ("identity_missing", "write_forbidden") else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_value_baseline_put failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/domain-packs")
async def org_domain_packs_route():
    """S3: list domain pack templates."""
    try:
        from core.api.core_facade import org_domain_packs

        return org_domain_packs()
    except Exception as e:
        logger.error("org_domain_packs failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/domain-packs/install")
async def org_domain_packs_install_route(request: Request, body: Dict[str, Any]):
    """S3: install a domain pack. Does not claim M4."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_domain_pack_install

        out = org_domain_pack_install(
            role=role,
            template_id=str(body.get("template_id") or ""),
            domain_id=str(body.get("domain_id") or ""),
            display_name=str(body.get("display_name") or ""),
        )
        if not out.get("ok"):
            code = 403 if out.get("reason") in ("identity_missing", "install_forbidden") else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_domain_pack_install failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/signoff/progress")
async def org_signoff_progress_get_route(request: Request):
    """S4: read signoff progress. m4_claim_allowed stays false."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_signoff_progress_get

        out = org_signoff_progress_get(role=role)
        if not out.get("ok"):
            raise HTTPException(status_code=403, detail=out)
        out["m4_claim_allowed"] = False
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_signoff_progress_get failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.put("/signoff/progress")
async def org_signoff_progress_put_route(request: Request, body: Dict[str, Any]):
    """S4: write oncall / dual-sign. Never flips m4_claim_allowed."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_signoff_progress_put

        out = org_signoff_progress_put(role=role, body=body or {})
        if not out.get("ok"):
            code = 403 if out.get("reason") in ("identity_missing", "write_forbidden") else 400
            raise HTTPException(status_code=code, detail=out)
        out["m4_claim_allowed"] = False
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_signoff_progress_put failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/rollback/scope")
async def org_rollback_scope():
    """V5: what rollback covers. Read-only."""
    try:
        from core.api.core_facade import org_rollback_scope as _scope

        view = _scope()
        view["one_click_any_change"] = False
        view["covers_edges"] = False
        return view
    except Exception as e:
        logger.error("org_rollback_scope failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/approvals/inbox")
async def org_approvals_inbox(
    request: Request,
    domain_id: str = Query("it-ops"),
    goal_id: str = Query("goal-it-ops-alert-sla"),
    kind: str = Query(""),
    offset: int = Query(0),
    limit: int = Query(20),
):
    """H1: read-only pending queue. Does not approve."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_approval_inbox

        out = await org_approval_inbox(
            role=role,
            domain_id=domain_id or "it-ops",
            goal_id=goal_id or "goal-it-ops-alert-sla",
            kind=kind or "",
            offset=offset,
            limit=limit,
        )
        if not out.get("ok"):
            code = 403 if out.get("reason") == "identity_missing" else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_approvals_inbox failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


def _h4_http(out: Dict[str, Any]) -> Dict[str, Any]:
    if out.get("reason") in ("identity_missing", "scan_forbidden", "audit_forbidden"):
        raise HTTPException(status_code=403, detail=out)
    return out


@router.get("/approvals/auto-rules")
async def org_approvals_auto_rules(request: Request):
    """H4: read-only rule switch. Default enabled=false."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_h4_rules

        return _h4_http(org_h4_rules(role=role))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_h4_rules failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/approvals/auto-audit")
async def org_approvals_auto_audit(
    request: Request,
    limit: int = Query(50),
):
    """H4: admin-only auto-pass audit. Not for ordinary FDE."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_h4_auto_audit

        return _h4_http(org_h4_auto_audit(role=role, limit=limit))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_h4_auto_audit failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/approvals/auto-pass")
async def org_approvals_auto_pass(
    request: Request,
    domain_id: str = Query("it-ops"),
):
    """H4: pass eligible queue items. Does not write live YAML."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_h4_auto_pass

        return _h4_http(await org_h4_auto_pass(role=role, domain_id=domain_id or "it-ops"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_h4_auto_pass failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


def _h5_http(out: Dict[str, Any]) -> Dict[str, Any]:
    if out.get("reason") in ("identity_missing", "approve_forbidden"):
        raise HTTPException(status_code=403, detail=out)
    return out


@router.get("/skills/drafts")
async def org_skill_drafts(request: Request, domain_id: str = Query("it-ops")):
    """H5: draft packs. Not listed until human approve."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_h5_drafts

        return _h5_http(org_h5_drafts(role=role, domain_id=domain_id or "it-ops"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_h5_drafts failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/skills/drafts")
async def org_skill_draft_create(
    request: Request,
    case_id: str = Query(""),
    domain_id: str = Query("it-ops"),
):
    """H5: create a draft from a skill_candidate case. Does not list it."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_h5_create_draft

        return _h5_http(
            org_h5_create_draft(role=role, case_id=case_id, domain_id=domain_id or "it-ops")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_h5_create_draft failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/ontology/gap-hints")
async def org_gap_hints_route(domain_id: str = Query("it-ops")):
    """Read-only repeated-failure hint. Does not write YAML."""
    try:
        from core.api.core_facade import org_gap_hints

        out = org_gap_hints(domain_id=domain_id or "it-ops")
        out["wrote_live_yaml"] = False
        out["m4_claim_allowed"] = False
        return out
    except Exception as e:
        logger.error("org_gap_hints failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/ontology/gap-previews")
async def org_gap_previews_route(domain_id: str = Query("it-ops")):
    """Read-only Diff for schema_gap cases. Does not create proposals or write YAML."""
    try:
        from core.api.core_facade import org_preview_schema_gaps

        return org_preview_schema_gaps(domain_id=domain_id or "it-ops")
    except Exception as e:
        logger.error("org_gap_previews failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/ontology/cases/cold")
async def org_cold_cases_route(domain_id: str = Query("it-ops"), limit: int = Query(20, ge=1, le=50)):
    """List cold-archived cases. Audit only; not injected."""
    try:
        from core.api.core_facade import org_list_cold_cases

        return org_list_cold_cases(domain_id=domain_id or "it-ops", limit=limit)
    except Exception as e:
        logger.error("org_cold_cases failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/ontology/cases/archive-cold")
async def org_archive_cold_route(request: Request, domain_id: str = Query("it-ops")):
    """Move low-yield cases to cold store. Does not delete or write live YAML."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_archive_cold_cases

        out = org_archive_cold_cases(role=role, domain_id=domain_id or "it-ops")
        if not out.get("ok") and out.get("reason") in ("identity_missing", "archive_forbidden"):
            raise HTTPException(status_code=403, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_archive_cold failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/ontology/gap-drafts")
async def org_gap_drafts_route(request: Request, domain_id: str = Query("it-ops")):
    """Draft from schema_gap cases via the existing proposal ledger. No live YAML."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_draft_schema_gaps

        out = await org_draft_schema_gaps(role=role, domain_id=domain_id or "it-ops")
        if not out.get("ok") and out.get("reason") in ("identity_missing", "draft_forbidden"):
            raise HTTPException(status_code=403, detail=out)
        if out.get("reason") == "edge_auto_apply_forbidden":
            raise HTTPException(status_code=409, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_gap_drafts failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/skills/drafts/bundle")
async def org_skill_bundle_route(request: Request, body: Dict[str, Any]):
    """Assemble existing drafts. No SKILL.md."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_skill_bundle

        out = org_skill_bundle(role=role, draft_ids=body.get("draft_ids") or [])
        if not out.get("ok"):
            code = 403 if out.get("reason") == "identity_missing" else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_skill_bundle failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/skills/drafts/{draft_id}/approve")
async def org_skill_draft_approve(draft_id: str, request: Request):
    """H5: admin lists the draft on the existing marketplace. Not automatic."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_h5_approve_draft

        return _h5_http(org_h5_approve_draft(role=role, draft_id=draft_id))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_h5_approve_draft failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/skills/drafts/{draft_id}/reject")
async def org_skill_draft_reject(draft_id: str, request: Request):
    """H5: reject a draft. Does not register."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_h5_reject_draft

        return _h5_http(org_h5_reject_draft(role=role, draft_id=draft_id))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_h5_reject_draft failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/approvals/{kind}/{item_id}/snapshot")
async def org_approvals_snapshot(
    kind: str,
    item_id: str,
    request: Request,
    domain_id: str = Query("it-ops"),
):
    """H1: read-only snapshot. Approve via existing routes only."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_approval_snapshot

        out = await org_approval_snapshot(
            kind, item_id, role=role, domain_id=domain_id or "it-ops"
        )
        if not out.get("ok"):
            code = 403 if out.get("reason") == "identity_missing" else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_approvals_snapshot failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/field-ops/live-unlock")
async def org_live_unlock(domain_id: str = Query("it-ops")):
    try:
        from core.api.core_facade import org_live_unlock_status

        return org_live_unlock_status(domain_id or "it-ops")
    except Exception as e:
        logger.error("org_live_unlock failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/interfaces/{domain_id}/materialize")
async def org_interface_materialize(domain_id: str):
    """Phase C1.5: copy spec to AIPLAT_HOME yaml. Does not write connector.live."""
    try:
        from core.api.core_facade import org_materialize_interface

        return org_materialize_interface(domain_id or "it-ops")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:300])
    except Exception as e:
        logger.error("org_interface_materialize failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/interfaces")
async def org_interfaces(domain_id: str = Query("")):
    """Phase C1.5: InterfaceSpec list (yaml, else connector.live)."""
    try:
        from core.api.core_facade import org_list_interfaces

        return org_list_interfaces(domain_id or "")
    except Exception as e:
        logger.error("org_interfaces failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/interfaces/{domain_id}")
async def org_interface_get(domain_id: str):
    try:
        from core.api.core_facade import org_get_interface

        return org_get_interface(domain_id or "it-ops")
    except Exception as e:
        logger.error("org_interface_get failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/interfaces/{domain_id}/actions/{action_id}")
async def org_interface_action_bound(domain_id: str, action_id: str):
    try:
        from core.api.core_facade import org_assert_action_interface

        out = org_assert_action_interface(domain_id, action_id)
        if out.get("status") == "need_action_id":
            raise HTTPException(status_code=400, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_interface_action_bound failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/usage/weekly")
async def org_usage_weekly_api(
    domain_id: str = Query(""),
    week: str = Query(""),
):
    try:
        from core.api.core_facade import org_usage_weekly

        return org_usage_weekly(domain_id or "", week or "")
    except Exception as e:
        logger.error("org_usage_weekly failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/posts")
async def org_posts():
    try:
        from core.api.core_facade import org_list_posts

        return org_list_posts()
    except Exception as e:
        logger.error("org_posts failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/posts/{post_id}")
async def org_post_get(post_id: str):
    try:
        from core.api.core_facade import org_get_post

        out = org_get_post(post_id)
        if out.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_post_get failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/channels/feishu/status")
async def org_feishu_status():
    try:
        from core.api.core_facade import org_ingress_status

        return org_ingress_status()
    except Exception as e:
        logger.error("org_feishu_status failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/channels/feishu/events")
async def org_feishu_events(request: Request):
    """Phase C2: Feishu/Lark inbound. Signature required. No second channel."""
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        from core.api.core_facade import org_ingest_feishu

        out = org_ingest_feishu(
            payload,
            headers={k: v for k, v in request.headers.items()},
            raw_body=raw,
        )
        code = int(out.get("http_status") or 200)
        if code >= 400:
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_feishu_events failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/events/previews")
async def org_event_previews_route(limit: int = Query(5, ge=1, le=20)):
    """List sandbox event previews. Does not start live IO."""
    try:
        from core.api.core_facade import org_event_previews

        return org_event_previews(limit=limit)
    except Exception as e:
        logger.error("org_event_previews failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/events/preview")
async def org_event_preview_route(request: Request, body: Dict[str, Any]):
    """Whitelist event sandbox preview. No second channel, no live run."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import org_event_preview_start

        out = org_event_preview_start(
            role=role,
            domain_id=str(body.get("domain_id") or ""),
            event_type=str(body.get("event_type") or ""),
        )
        if not out.get("ok"):
            code = 403 if out.get("reason") in ("identity_missing", "preview_forbidden") else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("org_event_preview failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/connectors/fetch")
async def org_connectors_fetch(body: Dict[str, Any]):
    """Canonical Org L5 fetch (D4 converged). Prefer this over FDE governance/fetch."""
    domain_id = str(body.get("domain_id") or "it-ops").strip() or "it-ops"
    entity_id = str(body.get("entity_id") or body.get("id") or "").strip()
    purpose = str(body.get("purpose") or "org_pilot").strip() or "org_pilot"
    try:
        from core.api.core_facade import governance_fetch_view

        return governance_fetch_view(domain_id, entity_id, purpose=purpose)
    except Exception as e:
        logger.error("org_connectors_fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/connectors/write-preview")
async def org_connectors_write_preview(body: Dict[str, Any]):
    domain_id = str(body.get("domain_id") or "it-ops").strip() or "it-ops"
    entity_id = str(body.get("entity_id") or body.get("id") or "").strip()
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else {}
    try:
        from core.api.core_facade import governance_write_preview

        return governance_write_preview(domain_id, entity_id, patch)
    except Exception as e:
        logger.error("org_connectors_write_preview failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])
