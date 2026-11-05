"""A3/A6 local — canonical /api/platform/apps/eval/store/* on standalone.

Honesty:
- Hosts store CRUD against local SQLite; Bearer JWT when auth required.
- Cross-tenant reads return 404. process_split_authorized remains false.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query, Request

from app.auth import require_bearer, tenant_or_404
from app.scoring.report_compare import compare_reports
from app.store import (
    create_report,
    create_set,
    get_report,
    get_set,
    list_reports,
    list_sets,
    store_health,
)


def _store(request: Request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise RuntimeError("store_not_initialized")
    return store


async def _store_healthz(request: Request) -> Dict[str, Any]:
    require_bearer(request)
    return {"data": store_health(_store(request))}


async def _list_sets(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    claims = require_bearer(request)
    tid = str(claims.get("tenant_id") or "")
    items = list_sets(_store(request), limit=limit, tenant_id=tid)
    return {"data": {"items": items, "total": len(items)}}


async def _create_set(request: Request) -> Dict[str, Any]:
    claims = require_bearer(request)
    tid = str(claims.get("tenant_id") or "")
    body: Dict[str, Any] = await request.json()
    row = create_set(
        _store(request),
        name=str(body.get("name") or "untitled"),
        version=str(body.get("version") or "0"),
        split=str(body.get("split") or "dev"),
        meta=body.get("meta") if isinstance(body.get("meta"), dict) else None,
        set_id=str(body.get("id") or "") or None,
        tenant_id=tid,
    )
    return {"data": row}


async def _get_set(request: Request, set_id: str) -> Dict[str, Any]:
    claims = require_bearer(request)
    tid = str(claims.get("tenant_id") or "")
    row = get_set(_store(request), set_id)
    if claims.get("auth_disabled"):
        return {"data": row or {"error": "not_found", "id": set_id}}
    return {"data": tenant_or_404(row, tid)}


async def _list_reports(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    claims = require_bearer(request)
    tid = str(claims.get("tenant_id") or "")
    items = list_reports(_store(request), limit=limit, tenant_id=tid)
    return {"data": {"items": items, "total": len(items)}}


async def _create_report(request: Request) -> Dict[str, Any]:
    claims = require_bearer(request)
    tid = str(claims.get("tenant_id") or "")
    body: Dict[str, Any] = await request.json()
    row = create_report(
        _store(request),
        run_ids=body.get("run_ids") if isinstance(body.get("run_ids"), list) else None,
        metrics=body.get("metrics") if isinstance(body.get("metrics"), dict) else None,
        scoring=body.get("scoring") if isinstance(body.get("scoring"), dict) else None,
        meta=body.get("meta") if isinstance(body.get("meta"), dict) else None,
        slices=body.get("slices") if isinstance(body.get("slices"), dict) else None,
        failures=body.get("failures") if isinstance(body.get("failures"), list) else None,
        report_id=str(body.get("id") or "") or None,
        tenant_id=tid,
    )
    return {"data": row}


async def _get_report(request: Request, report_id: str) -> Dict[str, Any]:
    claims = require_bearer(request)
    tid = str(claims.get("tenant_id") or "")
    row = get_report(_store(request), report_id)
    if claims.get("auth_disabled"):
        return {"data": row or {"error": "not_found", "id": report_id}}
    return {"data": tenant_or_404(row, tid)}


async def _compare_reports(request: Request) -> Dict[str, Any]:
    """P1b — compare two reports; comparable only if same composite_version."""
    claims = require_bearer(request)
    tid = str(claims.get("tenant_id") or "")
    body: Dict[str, Any] = await request.json()
    bid = str(body.get("baseline_id") or "").strip()
    cid = str(body.get("candidate_id") or "").strip()
    if not bid or not cid:
        raise HTTPException(status_code=422, detail="baseline_id and candidate_id required")
    store = _store(request)
    base = get_report(store, bid)
    cand = get_report(store, cid)
    if not claims.get("auth_disabled"):
        base = tenant_or_404(base, tid)
        cand = tenant_or_404(cand, tid)
    elif base is None or cand is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "baseline_id": bid, "candidate_id": cid},
        )
    return {"data": compare_reports(base, cand)}


def register_store_routes(application: FastAPI) -> None:
    prefix = "/api/platform/apps/eval/store"
    application.add_api_route(f"{prefix}/healthz", _store_healthz, methods=["GET"])
    application.add_api_route(f"{prefix}/sets", _list_sets, methods=["GET"])
    application.add_api_route(f"{prefix}/sets", _create_set, methods=["POST"])
    application.add_api_route(f"{prefix}/sets/{{set_id}}", _get_set, methods=["GET"])
    application.add_api_route(f"{prefix}/reports", _list_reports, methods=["GET"])
    application.add_api_route(f"{prefix}/reports", _create_report, methods=["POST"])
    # Static path before {report_id} so "compare" is not captured as an id.
    application.add_api_route(
        f"{prefix}/reports/compare", _compare_reports, methods=["POST"]
    )
    application.add_api_route(
        f"{prefix}/reports/{{report_id}}", _get_report, methods=["GET"]
    )


def _wire_store_routes(application: FastAPI) -> None:
    """Same-file caller for method_verify."""
    register_store_routes(application)
