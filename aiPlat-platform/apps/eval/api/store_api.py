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
    return {"data": {"items": items, "total": len(items)}}


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
    return {"data": {"items": items, "total": len(items)}}


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
