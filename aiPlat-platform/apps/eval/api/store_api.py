"""EVAL_V1 E2 — thin CRUD / migrate over EvalStore (canonical under /eval)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from auth.deps import require_auth
from apps.common_schemas import ItemResponse, ListResponse

router = APIRouter(prefix="/store", tags=["eval-store"])


@router.get("/healthz", response_model=ItemResponse)
async def store_health(
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_store_health

    return {"data": eval_store_health(tenant_id=tenant_id)}


@router.get("/sets", response_model=ListResponse)
async def list_sets(
    tenant_id: str = "",
    limit: int = Query(100, ge=1, le=1000),
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_store_list_sets

    items = eval_store_list_sets(tenant_id=tenant_id, limit=limit)
    # ListResponse is flat {items,total} — nesting under data zeros the list via response_model
    return {"items": items, "total": len(items)}


@router.post("/sets", response_model=ItemResponse)
async def create_set(
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_store_create_set

    row = eval_store_create_set(
        name=str(body.get("name") or "untitled"),
        version=str(body.get("version") or "0"),
        split=str(body.get("split") or "dev"),
        meta=body.get("meta") if isinstance(body.get("meta"), dict) else None,
        set_id=str(body.get("id") or "") or None,
        tenant_id=str(body.get("tenant_id") or ""),
    )
    return {"data": row}


@router.get("/sets/{set_id}", response_model=ItemResponse)
async def get_set(
    set_id: str,
    tenant_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_store_get_set

    row = eval_store_get_set(set_id, tenant_id=tenant_id)
    return {"data": row or {"error": "not_found", "id": set_id}}


@router.get("/tasks", response_model=ListResponse)
async def list_tasks(
    set_id: str = "",
    tenant_id: str = "",
    limit: int = Query(500, ge=1, le=5000),
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_store_list_tasks

    items = eval_store_list_tasks(set_id=set_id, tenant_id=tenant_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/tasks", response_model=ItemResponse)
async def create_task(
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_store_create_task

    try:
        row = eval_store_create_task(
            set_id=str(body.get("set_id") or ""),
            input_data=body.get("input") if isinstance(body.get("input"), dict) else None,
            expected=body.get("expected") if isinstance(body.get("expected"), dict) else None,
            rubric=body.get("rubric") if isinstance(body.get("rubric"), dict) else None,
            tags=body.get("tags") if isinstance(body.get("tags"), list) else None,
            hard_negative=bool(body.get("hard_negative")),
            source=str(body.get("source") or ""),
            task_id=str(body.get("id") or "") or None,
            tenant_id=str(body.get("tenant_id") or ""),
        )
    except ValueError as e:
        return {"data": {"ok": False, "error": str(e)}}
    return {"data": row}


@router.post("/migrate/code-review-gold", response_model=ItemResponse)
async def migrate_code_review_gold(
    body: Optional[Dict[str, Any]] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """Import code-review-gold YAML → eval_sets + eval_tasks (idempotent)."""
    from core.api.core_facade import eval_store_import_code_review_gold

    body = body or {}
    try:
        out = eval_store_import_code_review_gold(
            gold_dir=str(body.get("gold_dir") or "") or None,
            tenant_id=str(body.get("tenant_id") or ""),
            set_name=str(body.get("set_name") or "code-review-gold"),
            set_version=str(body.get("set_version") or "v0-seed"),
        )
    except FileNotFoundError as e:
        return {"data": {"ok": False, "error": str(e)}}
    return {"data": out}


@router.post("/bootstrap-e3", response_model=ItemResponse)
async def bootstrap_e3(
    body: Optional[Dict[str, Any]] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """EVAL_V1 E3: import ≥15 gold tasks + open solo review label queue."""
    from core.api.core_facade import eval_bootstrap_e3_gold

    body = body or {}
    try:
        out = eval_bootstrap_e3_gold(
            tenant_id=str(body.get("tenant_id") or "eval-v1"),
            gold_dir=str(body.get("gold_dir") or "") or None,
            annotator=str(body.get("annotator") or "solo_reviewer"),
        )
    except FileNotFoundError as e:
        return {"data": {"ok": False, "error": str(e)}}
    return {"data": out}


@router.get("/e3-status", response_model=ItemResponse)
async def get_e3_status(
    tenant_id: str = "eval-v1",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_e3_status

    return {"data": eval_e3_status(tenant_id=tenant_id)}


@router.get("/judges", response_model=ListResponse)
async def list_judges(
    tenant_id: str = "eval-v1",
    limit: int = Query(50, ge=1, le=200),
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_list_judges

    items = eval_list_judges(tenant_id=tenant_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/calibrate-e4", response_model=ItemResponse)
async def calibrate_e4(
    body: Optional[Dict[str, Any]] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """EVAL_V1 E4: judge v1 k-repeat calibration report (not an accuracy claim)."""
    from core.api.core_facade import eval_run_e4_calibration

    body = body or {}
    try:
        out = eval_run_e4_calibration(
            tenant_id=str(body.get("tenant_id") or "eval-v1"),
            set_id=str(body.get("set_id") or ""),
            k=int(body.get("k") or 3),
            limit=int(body.get("limit") or 500),
        )
    except ValueError as e:
        return {"data": {"ok": False, "error": str(e)}}
    return {"data": out}


@router.post("/gate-e5", response_model=ItemResponse)
async def gate_e5(
    body: Optional[Dict[str, Any]] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """EVAL_V1 E5: local engineering gate (pr/nightly/release); not accuracy/G2a claim."""
    from core.api.core_facade import eval_run_e5_gate

    body = body or {}
    limit_raw = body.get("limit")
    limit = int(limit_raw) if limit_raw is not None and str(limit_raw) != "" else None
    try:
        out = eval_run_e5_gate(
            mode=str(body.get("mode") or "pr"),
            tenant_id=str(body.get("tenant_id") or "eval-v1"),
            set_id=str(body.get("set_id") or ""),
            baseline=str(body.get("baseline") or "gold"),
            candidate=str(body.get("candidate") or "local"),
            limit=limit,
        )
    except ValueError as e:
        return {"data": {"ok": False, "error": str(e)}}
    return {"data": out}


@router.get("/g2a-status", response_model=ItemResponse)
async def get_g2a_status(
    tenant_id: str = "eval-v1",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_g2a_status

    return {"data": eval_g2a_status(tenant_id=tenant_id)}


@router.get("/review-queue", response_model=ItemResponse)
async def get_review_queue(
    tenant_id: str = "eval-v1",
    annotator: str = "solo_reviewer",
    limit: int = Query(100, ge=1, le=500),
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_list_review_queue

    return {
        "data": eval_list_review_queue(
            tenant_id=tenant_id, annotator=annotator, limit=limit
        )
    }


@router.post("/review-queue/preannotate", response_model=ItemResponse)
async def preannotate_queue(
    body: Optional[Dict[str, Any]] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """AI pre-annotation only — does not adjudicate (D5)."""
    from core.api.core_facade import eval_preannotate_review_queue

    body = body or {}
    try:
        out = eval_preannotate_review_queue(
            tenant_id=str(body.get("tenant_id") or "eval-v1"),
            annotator=str(body.get("annotator") or "solo_reviewer"),
            limit=int(body.get("limit") or 500),
        )
    except ValueError as e:
        return {"data": {"ok": False, "error": str(e)}}
    return {"data": out}


@router.post("/labels/{label_id}/adjudicate", response_model=ItemResponse)
async def adjudicate_label_api(
    label_id: str,
    body: Optional[Dict[str, Any]] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """Solo human adjudication (D5). Required before lock_v0 / G2a."""
    from core.api.core_facade import eval_adjudicate_label

    body = body or {}
    if "pass" not in body and "passed" not in body:
        return {"data": {"ok": False, "error": "pass (bool) required"}}
    passed = body.get("pass") if "pass" in body else body.get("passed")
    try:
        out = eval_adjudicate_label(
            label_id,
            passed=bool(passed),
            notes=str(body.get("notes") or ""),
            rationale=str(body.get("rationale") or ""),
            tenant_id=str(body.get("tenant_id") or "eval-v1"),
        )
    except ValueError as e:
        return {"data": {"ok": False, "error": str(e)}}
    return {"data": out}


@router.post("/lock-v0", response_model=ItemResponse)
async def lock_v0_api(
    body: Optional[Dict[str, Any]] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """Lock gold v0 when ≥30 tasks + ≥30 solo adjudicated. Not an accuracy claim."""
    from core.api.core_facade import eval_lock_v0

    body = body or {}
    return {"data": eval_lock_v0(tenant_id=str(body.get("tenant_id") or "eval-v1"))}


@router.post("/gate-g2a", response_model=ItemResponse)
async def gate_g2a(
    body: Optional[Dict[str, Any]] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """EVAL_V1 G2a: local gate claim after v0 lock; accuracy_claim stays false."""
    from core.api.core_facade import eval_run_g2a_gate

    body = body or {}
    limit_raw = body.get("limit")
    limit = int(limit_raw) if limit_raw is not None and str(limit_raw) != "" else None
    try:
        out = eval_run_g2a_gate(
            mode=str(body.get("mode") or "nightly"),
            tenant_id=str(body.get("tenant_id") or "eval-v1"),
            set_id=str(body.get("set_id") or ""),
            limit=limit,
        )
    except ValueError as e:
        return {"data": {"ok": False, "error": str(e)}}
    return {"data": out}


@router.get("/gates", response_model=ListResponse)
async def list_gates(
    tenant_id: str = "eval-v1",
    limit: int = Query(50, ge=1, le=200),
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_list_gates

    items = eval_list_gates(tenant_id=tenant_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/gates/{gate_id}", response_model=ItemResponse)
async def get_gate(
    gate_id: str,
    tenant_id: str = "eval-v1",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_get_gate

    row = eval_get_gate(gate_id, tenant_id=tenant_id)
    return {"data": row or {"error": "not_found", "id": gate_id}}


@router.get("/reports/{report_id}", response_model=ItemResponse)
async def get_store_report(
    report_id: str,
    tenant_id: str = "eval-v1",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import eval_get_report

    row = eval_get_report(report_id, tenant_id=tenant_id)
    return {"data": row or {"error": "not_found", "id": report_id}}
