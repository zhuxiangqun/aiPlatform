"""
KB Evaluation core stubs — EVAL_V1 E1 legacy shim.

Canonical implementation: /api/platform/apps/eval/kb-eval/*
These core routes remain for backward compatibility and return deprecation metadata.
"""
from typing import Any, Dict

from fastapi import APIRouter, Query
from starlette.responses import JSONResponse

router = APIRouter(prefix="/kb-eval", tags=["kb-eval"])

_SUCCESSOR = "/api/platform/apps/eval/kb-eval"
_DEPRECATION = {
    "deprecated": True,
    "successor_prefix": _SUCCESSOR,
    "detail": "EVAL_V1: use /api/platform/apps/eval/kb-eval; this core path is a legacy shim",
}


def _shim(payload: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    body = {**_DEPRECATION, **payload}
    resp = JSONResponse(content=body, status_code=status_code)
    resp.headers["Deprecation"] = "true"
    resp.headers["X-Aiplat-Eval-Canonical-Prefix"] = "/api/platform/apps/eval"
    resp.headers["Link"] = f'<{_SUCCESSOR}>; rel="successor-version"'
    resp.headers["Warning"] = (
        '299 - "EVAL_V1: use /api/platform/apps/eval/kb-eval; this path is a legacy shim"'
    )
    return resp


@router.get("/samples", response_model=None)
async def list_eval_samples(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return _shim({"samples": [], "total": 0, "limit": limit, "offset": offset})


@router.post("/samples", response_model=None)
async def create_eval_sample():
    return _shim({"detail": "Not Implemented", "sample": None})


@router.delete("/samples/{sample_id}", response_model=None)
async def delete_eval_sample(sample_id: str):
    return _shim({"detail": "Not Implemented", "sample_id": sample_id})


@router.post("/run", response_model=None)
async def run_eval():
    return _shim({"detail": "Not Implemented"})


@router.get("/reports/series", response_model=None)
async def get_reports_time_series(days: int = Query(30, ge=1, le=365)):
    return _shim({"series": [], "days": days})
