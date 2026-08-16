"""
KB Evaluation stubs — back-end API for retrieval evaluation and quality feedback pages.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Query

router = APIRouter(prefix="/kb-eval", tags=["kb-eval"])


@router.get("/samples", response_model=Dict[str, Any])
async def list_eval_samples(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return {"samples": [], "total": 0, "limit": limit, "offset": offset}


@router.post("/samples", response_model=Dict[str, Any])
async def create_eval_sample():
    return {"detail": "Not Implemented", "sample": None}


@router.delete("/samples/{sample_id}", response_model=Dict[str, Any])
async def delete_eval_sample(sample_id: str):
    return {"detail": "Not Implemented", "sample_id": sample_id}


@router.post("/run", response_model=Dict[str, Any])
async def run_eval():
    return {"detail": "Not Implemented"}


@router.get("/reports/series", response_model=Dict[str, Any])
async def get_reports_time_series(days: int = Query(30, ge=1, le=365)):
    return {"series": [], "days": days}
