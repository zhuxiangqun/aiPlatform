"""KB Evaluation API — thin HTTP over CoreFacade kb_eval_* (ARCH_CONSOLIDATION v1.1)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from apps.common_schemas import StatusResponse, ItemResponse

router = APIRouter(prefix="/kb-eval", tags=["kb-eval"])


@router.get("/samples", response_model=ItemResponse)
async def list_samples(limit: int = 100, offset: int = 0, tag: Optional[str] = None):
    from core.api.core_facade import kb_eval_list_samples

    return kb_eval_list_samples(limit=limit, offset=offset, tag=tag)


@router.post("/samples", response_model=StatusResponse)
async def create_sample(body: Dict[str, Any]):
    from core.api.core_facade import kb_eval_create_sample

    return kb_eval_create_sample(body)


@router.delete("/samples/{sample_id}", response_model=StatusResponse)
async def delete_sample(sample_id: str):
    from core.api.core_facade import kb_eval_delete_sample

    return kb_eval_delete_sample(sample_id)


@router.post("/run", response_model=StatusResponse)
async def run_evaluation(body: Dict[str, Any]):
    from core.api.core_facade import kb_eval_run

    try:
        return await kb_eval_run(body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reports", response_model=ItemResponse)
async def list_reports(limit: int = 50, offset: int = 0):
    from core.api.core_facade import kb_eval_list_reports

    return kb_eval_list_reports(limit=limit, offset=offset)


@router.post("/samples/import", response_model=StatusResponse)
async def import_samples_csv(file: UploadFile = File(...)):
    from core.api.core_facade import kb_eval_import_csv_text

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    try:
        return kb_eval_import_csv_text(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reports/series", response_model=ItemResponse)
async def reports_time_series(days: int = 30):
    from core.api.core_facade import kb_eval_reports_series

    return kb_eval_reports_series(days=days)


@router.get("/reports/compare", response_model=ItemResponse)
async def compare_reports(session_a: str = "", session_b: str = ""):
    from core.api.core_facade import kb_eval_compare_reports

    return kb_eval_compare_reports(session_a=session_a, session_b=session_b)
