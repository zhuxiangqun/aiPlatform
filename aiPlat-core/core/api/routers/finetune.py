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


@router.delete("/datasets/{dataset_id}", response_model=Dict[str, Any])
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


@router.delete("/jobs/{job_id}", response_model=Dict[str, Any])
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


# ── RL Training ──────────────────────────────────────────────────────────

@router.post("/train")
async def start_training(body: Dict[str, Any]) -> Dict[str, Any]:
    """Start an RL training job.

    Body:
      - base_model: str (e.g. "qwen2.5-coder:7b")
      - dataset_id: str
      - num_iterations: int (default: 1)
      - episodes_per_iter: int (default: 8)
    """
    try:
        from core.harness.training.rl_trainer import get_rl_trainer
        base_model = body.get("base_model", "")
        dataset_id = body.get("dataset_id", "")
        if not base_model:
            raise HTTPException(status_code=400, detail="base_model is required")

        trainer = get_rl_trainer(base_model=base_model)
        run = await trainer.train(
            num_iterations=body.get("num_iterations", 1),
            episodes_per_iter=body.get("episodes_per_iter", 8),
        )
        return {
            "status": run.status,
            "iterations": run.iterations,
            "episodes": run.total_episodes,
            "avg_reward": run.avg_reward,
            "avg_loss": getattr(run, "avg_loss", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/train/{job_id}")
async def get_training_status(job_id: str) -> Dict[str, Any]:
    """Get RL training job status."""
    try:
        from core.harness.training.rl_trainer import get_rl_trainer
        trainer = get_rl_trainer(base_model="")
        status = getattr(trainer, "_latest_run", None)
        if status:
            return {
                "job_id": job_id,
                "status": status.status if hasattr(status, 'status') else "running",
                "iterations": getattr(status, 'iterations', 0),
                "episodes": getattr(status, 'total_episodes', 0),
                "avg_reward": getattr(status, 'avg_reward', 0),
            }
        return {"job_id": job_id, "status": "unknown"}
    except Exception as e:
        return {"job_id": job_id, "status": "error", "error": str(e)[:200]}


# ── Knowledge Distillation ───────────────────────────────────────────────

@router.post("/distill")
async def start_distillation(body: Dict[str, Any]) -> Dict[str, Any]:
    """Start a knowledge distillation job (Teacher→Student).

    Body:
      - teacher_model: str (e.g. "qwen2.5-coder:32b")
      - student_model: str (e.g. "qwen2.5-coder:7b")
      - dataset_id: str
      - temperature: float (default: 2.0)
      - alpha: float (default: 0.5, hard target weight)
      - mode: str (default: "lora", "lora"|"full")
      - epochs: int (default: 3)
    """
    try:
        from core.harness.training.distillation import get_distillation_engine
        engine = get_distillation_engine()
        job_id = await engine.distill(
            teacher_model=body.get("teacher_model", ""),
            student_model=body.get("student_model", ""),
            dataset_id=body.get("dataset_id", ""),
            temperature=float(body.get("temperature", 2.0)),
            alpha=float(body.get("alpha", 0.5)),
            mode=body.get("mode", "lora"),
            epochs=int(body.get("epochs", 3)),
        )
        return {"job_id": job_id, "status": "running"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/distill/{job_id}")
async def get_distillation_status(job_id: str) -> Dict[str, Any]:
    """Get knowledge distillation job status."""
    try:
        from core.harness.training.distillation import get_distillation_engine
        engine = get_distillation_engine()
        status = engine.get_status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail="Job not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        return {"job_id": job_id, "status": "error", "error": str(e)[:200]}


@router.get("/distill")
async def list_distillation_jobs() -> Dict[str, Any]:
    """List all distillation jobs."""
    try:
        from core.harness.training.distillation import get_distillation_engine
        engine = get_distillation_engine()
        jobs = engine.list_jobs()
        return {"jobs": jobs, "total": len(jobs)}
    except Exception as e:
        return {"jobs": [], "total": 0, "error": str(e)[:200]}


# ── From-Scratch Training ────────────────────────────────────────────────

@router.post("/scratch")
async def start_scratch_training(body: Dict[str, Any]) -> Dict[str, Any]:
    """Start a from-scratch model training job (random initialization).

    Body:
      - model_architecture: str (e.g. "gpt2", "pythia-160m")
      - dataset_id: str
      - output_model_name: str (optional)
      - epochs: int (default: 3)
      - batch_size: int (default: 4)
      - learning_rate: float (default: 5e-5)
    """
    try:
        from core.harness.training.full_training import get_full_training_engine, FullTrainingConfig
        engine = get_full_training_engine()
        config = FullTrainingConfig(
            model_architecture=body.get("model_architecture", "gpt2"),
            dataset_id=body.get("dataset_id", ""),
            output_model_name=body.get("output_model_name", ""),
            epochs=int(body.get("epochs", 3)),
            batch_size=int(body.get("batch_size", 4)),
            learning_rate=float(body.get("learning_rate", 5e-5)),
        )
        job_id = await engine.train_from_scratch(config)
        return {"job_id": job_id, "status": "running"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/scratch/{job_id}")
async def get_scratch_status(job_id: str) -> Dict[str, Any]:
    """Get from-scratch training job status."""
    try:
        from core.harness.training.full_training import get_full_training_engine
        engine = get_full_training_engine()
        status = engine.get_status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail="Job not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        return {"job_id": job_id, "status": "error", "error": str(e)[:200]}


@router.get("/scratch")
async def list_scratch_jobs() -> Dict[str, Any]:
    """List all from-scratch training jobs."""
    try:
        from core.harness.training.full_training import get_full_training_engine
        engine = get_full_training_engine()
        jobs = engine.list_jobs()
        return {"jobs": jobs, "total": len(jobs)}
    except Exception as e:
        return {"jobs": [], "total": 0, "error": str(e)[:200]}


def _local_provider():
    """Lazy load LocalFineTuneProvider class to avoid MLX import errors."""
    from core.harness.finetune.providers.local import LocalFineTuneProvider
    return LocalFineTuneProvider
