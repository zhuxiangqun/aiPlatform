"""
Fine-tuning API router — 数据集管理 + 微调作业 + Provider 查询。
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from core.schemas_finetune import (
    DatasetCreateRequest, DatasetUpdateRequest, DatasetImportRequest,
    DatasetResponse, DatasetListResponse, DatasetPreviewResponse,
    JobCreateRequest, JobResponse, JobListResponse,
    ProviderInfo, ProviderListResponse, FineTuneProvider,
)
from core.harness.finetune.dataset_manager import DatasetManager
from core.harness.finetune.job_manager import JobManager

router = APIRouter(prefix="/finetune", tags=["finetune"])

# ── Lazy singletons ──────────────────────────────────────────────────

_dataset_mgr: DatasetManager | None = None
_job_mgr: JobManager | None = None


def _get_dataset_mgr() -> DatasetManager:
    global _dataset_mgr
    if _dataset_mgr is None:
        _dataset_mgr = DatasetManager()
    return _dataset_mgr


def _get_job_mgr() -> JobManager:
    global _job_mgr
    if _job_mgr is None:
        _job_mgr = JobManager()
    return _job_mgr


# ── Datasets ──────────────────────────────────────────────────────────

@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets(limit: int = 100, offset: int = 0):
    return _get_dataset_mgr().list_all(limit=limit, offset=offset)


@router.post("/datasets", response_model=DatasetResponse)
async def create_dataset(req: DatasetCreateRequest):
    return _get_dataset_mgr().create(req)


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(dataset_id: str):
    ds = _get_dataset_mgr().get(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return ds


@router.put("/datasets/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(dataset_id: str, req: DatasetUpdateRequest):
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.description is not None:
        updates["description"] = req.description
    ds = _get_dataset_mgr().update(dataset_id, updates)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return ds


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str):
    ok = _get_dataset_mgr().delete(dataset_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return {"status": "deleted", "id": dataset_id}


@router.post("/datasets/{dataset_id}/import", response_model=DatasetResponse)
async def import_dataset(dataset_id: str, req: DatasetImportRequest):
    try:
        return _get_dataset_mgr().import_jsonl(dataset_id, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/datasets/{dataset_id}/preview", response_model=DatasetPreviewResponse)
async def preview_dataset(dataset_id: str, limit: int = 100):
    try:
        return _get_dataset_mgr().preview(dataset_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Jobs ─────────────────────────────────────────────────────────────

@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(limit: int = 100, offset: int = 0):
    return _get_job_mgr().list_all(limit=limit, offset=offset)


@router.post("/jobs", response_model=JobResponse)
async def create_job(req: JobCreateRequest):
    try:
        return _get_job_mgr().create(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    job = _get_job_mgr().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    ok = _get_job_mgr().cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found or already completed")
    return {"status": "cancelled", "id": job_id}


# ── Providers ────────────────────────────────────────────────────────

@router.get("/providers", response_model=ProviderListResponse)
async def list_providers():
    from core.harness.finetune.providers.deepseek import DeepSeekFineTuneProvider
    providers = []
    for prov_cls, name in [
        (DeepSeekFineTuneProvider, FineTuneProvider.DEEPSEEK),
        (_local_provider, FineTuneProvider.LOCAL),  # class/constructor, not instance
    ]:
        try:
            p = prov_cls()
            quota = p.check_quota()
            providers.append(ProviderInfo(
                name=name,
                display_name=p.display_name,
                available=p.available,
                quota_total=quota.get("total", 0),
                quota_used=quota.get("used", 0),
                supported_base_models=p.supported_base_models,
                estimated_cost_per_job=p.estimate_cost(100),
            ))
        except Exception as e:
            providers.append(ProviderInfo(
                name=name,
                display_name="本地 LoRA 微调 (MLX)" if name == FineTuneProvider.LOCAL else "DeepSeek",
                available=False,
                supported_base_models=[],
                estimated_cost_per_job="N/A",
            ))
    return ProviderListResponse(providers=providers)


def _local_provider():
    """Lazy load LocalFineTuneProvider class to avoid MLX import errors."""
    from core.harness.finetune.providers.local import LocalFineTuneProvider
    return LocalFineTuneProvider
