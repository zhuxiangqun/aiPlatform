"""DIAGNOSIS_V1 C1 canonical API — Case / Evidence / Report (no remediate)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from auth.deps import require_auth
from apps.common_schemas import ItemResponse, ListResponse, StatusResponse

# Self-prefix so static path-contract guard resolves full
# /api/platform/apps/diagnosis/... even when parent router.py basename collides.
router = APIRouter(prefix="/diagnosis", tags=["diagnosis-cases"])


def _detail(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _tenant(body: Optional[Dict[str, Any]] = None, tenant_id: str = "") -> str:
    if tenant_id:
        return tenant_id.strip()
    if isinstance(body, dict):
        return str(body.get("tenant_id") or "").strip()
    return ""


@router.get("/healthz", response_model=ItemResponse)
async def healthz(
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_health

    return {"data": diagnosis_health(tenant_id=tenant_id)}


@router.get("/metrics/fixtures", response_model=ItemResponse)
async def metrics_fixtures(
    limit: int = Query(10, ge=1, le=50),
    blind: bool = Query(True),
    subset: str = Query("core", pattern="^(core|adversarial|all)$"),
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_fixture_metrics

    try:
        out = diagnosis_fixture_metrics(limit=limit, blind=blind, subset=subset)
    except ValueError as e:
        raise _detail("invalid_subset", str(e), 422)
    return {"data": out}


@router.post("/cases", response_model=ItemResponse)
async def create_case(
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_create_case

    if body.get("accuracy_claim") is True:
        raise _detail("accuracy_claim_forbidden", "accuracy_claim must remain false", 422)
    try:
        row = diagnosis_create_case(
            scenario=str(body.get("scenario") or ""),
            subject_ref=str(body.get("subject_ref") or ""),
            tenant_id=_tenant(body),
            baseline_ref=(str(body["baseline_ref"]) if body.get("baseline_ref") is not None else None),
            case_id=str(body.get("id") or "") or None,
            meta=body.get("meta") if isinstance(body.get("meta"), dict) else None,
        )
    except ValueError as e:
        code = str(e)
        if code == "invalid_scenario":
            raise _detail("invalid_scenario", "scenario must be run_failure|version_regression")
        if code == "missing_subject":
            raise _detail("missing_subject", "subject_ref is required")
        raise _detail("invalid_request", code)
    return {"data": row}


@router.get("/cases", response_model=ListResponse)
async def list_cases(
    tenant_id: str = "",
    limit: int = Query(100, ge=1, le=1000),
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_list_cases

    items = diagnosis_list_cases(tenant_id=tenant_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/cases/{case_id}", response_model=ItemResponse)
async def get_case(
    case_id: str,
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_get_case

    row = diagnosis_get_case(case_id, tenant_id=tenant_id)
    if not row:
        raise _detail("case_not_found", "case not found", 404)
    return {"data": row}


@router.post("/cases/{case_id}/collect", response_model=ItemResponse)
async def collect(
    case_id: str,
    body: Optional[Dict[str, Any]] = None,
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_collect

    tid = _tenant(body, tenant_id)
    try:
        out = diagnosis_collect(case_id, tenant_id=tid)
    except KeyError:
        raise _detail("case_not_found", "case not found", 404)
    return {"data": out}


@router.get("/cases/{case_id}/evidence", response_model=ItemResponse)
async def get_evidence(
    case_id: str,
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_get_case, diagnosis_get_evidence

    if not diagnosis_get_case(case_id, tenant_id=tenant_id):
        raise _detail("case_not_found", "case not found", 404)
    bundle = diagnosis_get_evidence(case_id, tenant_id=tenant_id) or {
        "evidence": [],
        "payload": {},
    }
    return {"data": {"items": list(bundle.get("evidence") or []), "bundle": bundle}}


@router.get("/cases/{case_id}/findings", response_model=ItemResponse)
async def get_findings(
    case_id: str,
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_get_case, diagnosis_get_report

    if not diagnosis_get_case(case_id, tenant_id=tenant_id):
        raise _detail("case_not_found", "case not found", 404)
    bundle = diagnosis_get_report(case_id, tenant_id=tenant_id)
    items = list((bundle or {}).get("findings") or [])
    return {"data": {"items": items, "total": len(items)}}


@router.get("/cases/{case_id}/hypotheses", response_model=ItemResponse)
async def get_hypotheses(
    case_id: str,
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_get_case, diagnosis_get_report

    if not diagnosis_get_case(case_id, tenant_id=tenant_id):
        raise _detail("case_not_found", "case not found", 404)
    bundle = diagnosis_get_report(case_id, tenant_id=tenant_id)
    items = list((bundle or {}).get("hypotheses") or [])
    return {"data": {"items": items, "total": len(items)}}


@router.get("/cases/{case_id}/report", response_model=ItemResponse)
async def get_or_build_report(
    case_id: str,
    tenant_id: str = "",
    rebuild: bool = Query(False),
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import (
        diagnosis_get_case,
        diagnosis_get_report,
        diagnosis_run_report,
    )

    if not diagnosis_get_case(case_id, tenant_id=tenant_id):
        raise _detail("case_not_found", "case not found", 404)
    if not rebuild:
        existing = diagnosis_get_report(case_id, tenant_id=tenant_id)
        if existing:
            return {"data": existing}
    try:
        out = diagnosis_run_report(case_id, tenant_id=tenant_id)
    except RuntimeError as e:
        if str(e) == "case_not_ready":
            raise _detail("case_not_ready", "collect evidence before report", 409)
        raise
    return {"data": out}


@router.post("/cases/{case_id}/recommendations", response_model=ItemResponse)
async def recommendations(
    case_id: str,
    body: Optional[Dict[str, Any]] = None,
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import diagnosis_recommendations

    body = body or {}
    if body.get("auto_execute") is True:
        raise _detail("auto_execute_forbidden", "auto_execute must be false", 422)
    if body.get("accuracy_claim") is True:
        raise _detail("accuracy_claim_forbidden", "accuracy_claim must remain false", 422)
    tid = _tenant(body, tenant_id)
    try:
        out = diagnosis_recommendations(case_id, tenant_id=tid)
    except KeyError:
        raise _detail("case_not_found", "case not found", 404)
    except RuntimeError as e:
        if str(e) == "case_not_ready":
            raise _detail("case_not_ready", "report required before recommendations", 409)
        raise
    return {"data": out}


@router.post("/cases/{case_id}/remediate", response_model=StatusResponse)
async def remediate_forbidden(
    case_id: str,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    raise _detail(
        "auto_execute_forbidden",
        "remediate is out of product scope; recommendations only",
        422,
    )
