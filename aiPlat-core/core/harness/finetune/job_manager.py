"""
JobManager — 微调作业生命周期管理。

流程:
  1. 检查 Provider 可用性 + 配额
  2. 数据集快照
  3. 上传文件到 Provider
  4. 提交微调作业
  5. 后台轮询直到完成
  6. 注册模型到 infra ModelManager
  7. 超时检测（2h 无更新 → failed）
"""

from __future__ import annotations
import logging

import asyncio as _asyncio
import json
import os
import time as _time
import uuid as _uuid

import asyncio as _asyncio
import json as _json
import os as _os
import time as _time
import uuid as _uuid
from pathlib import Path as _Path
from typing import Any, Dict, Optional

from core.schemas_finetune import (
    JobStatus, FineTuneProvider, JobCreateRequest, JobResponse, JobListResponse,
    TEMPLATE_HYPERPARAMS, FineTuneTemplate,
)
from core.harness.finetune.dataset_manager import DatasetManager
from core.harness.finetune.providers.deepseek import DeepSeekFineTuneProvider


# Unified status mapping: DeepSeek API status → our JobStatus
_DS_STATUS_MAP = {
    "validating_files": JobStatus.VALIDATING,
    "queued": JobStatus.QUEUED,
    "running": JobStatus.TRAINING,
    "succeeded": JobStatus.COMPLETED,
    "failed": JobStatus.FAILED,
    "cancelled": JobStatus.CANCELLED,
}

_JOB_TIMEOUT_SECONDS = 2 * 3600  # 2 hours


class JobManager:
    """Manage the full lifecycle of fine-tuning jobs."""

    def __init__(self, base_dir: str = ""):
        self._base = _Path(base_dir or _os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "finetune_jobs"
        self._base.mkdir(parents=True, exist_ok=True)
        self._meta_path = self._base / "jobs_meta.json"
        self._dataset_mgr = DatasetManager(base_dir)

    # ── Meta storage ──────────────────────────────────────────────────

    def _read_meta(self) -> Dict[str, dict]:
        if not self._meta_path.exists():
            return {}
        try:
            return _json.loads(self._meta_path.read_text())
        except Exception:
            return {}

    def _write_meta(self, meta: Dict[str, dict]) -> None:
        self._meta_path.write_text(_json.dumps(meta, ensure_ascii=False, indent=2))

    # ── Provider factory ──────────────────────────────────────────────

    def _get_provider(self, provider: FineTuneProvider):
        if provider == FineTuneProvider.DEEPSEEK:
            return DeepSeekFineTuneProvider()
        if provider == FineTuneProvider.LOCAL:
            from core.harness.finetune.providers.local import LocalFineTuneProvider
            return LocalFineTuneProvider()
        raise ValueError(f"Unsupported provider: {provider}")

    # ── CRUD ──────────────────────────────────────────────────────────

    def create(self, req: JobCreateRequest) -> JobResponse:
        meta = self._read_meta()

        # Validate dataset exists
        dataset = self._dataset_mgr.get(req.dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {req.dataset_id} not found")
        if dataset.sample_count < 10:
            raise ValueError(f"Dataset has only {dataset.sample_count} samples (minimum 10)")

        # Validate provider available
        prov = self._get_provider(req.provider)
        if not prov.available:
            raise ValueError(f"Provider {req.provider.value} is not available (no API key)")

        # Check provider quota
        quota = prov.check_quota()
        if quota.get("available", 0) <= 0:
            raise ValueError(f"Provider {req.provider.value} has no available quota ({quota.get('used',0)}/{quota.get('total',0)} used)")

        # Build model name
        base = req.base_model.strip()
        ds_name = dataset.name.replace(" ", "-").lower()[:30]
        ts = _time.strftime("%Y%m%d%H%M")
        result_model = req.custom_name or f"{base}:ft-{ds_name}:{ts}"

        # Resolve hyperparams from template
        hp = dict(TEMPLATE_HYPERPARAMS.get(req.template.value, {}))
        hp.update(req.hyperparams or {})

        jid = _uuid.uuid4().hex[:12]
        now = _time.time()
        entry = {
            "id": jid,
            "base_model": base,
            "dataset_id": req.dataset_id,
            "dataset_name": dataset.name,
            "provider": req.provider.value,
            "provider_job_id": "",
            "result_model": result_model,
            "status": JobStatus.QUEUED.value,
            "template": req.template.value,
            "hyperparams": hp,
            "error": "",
            "sample_count": dataset.sample_count,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "estimated_duration_seconds": dataset.sample_count * 2,  # rough estimate
            "estimated_cost": prov.estimate_cost(dataset.sample_count, hp.get("epochs", 3)),
        }
        meta[jid] = entry
        self._write_meta(meta)

        # Start background execution
        _asyncio.ensure_future(self._execute(jid))

        return JobResponse(**entry)

    def get(self, job_id: str) -> Optional[JobResponse]:
        meta = self._read_meta()
        entry = meta.get(job_id)
        return JobResponse(**entry) if entry else None

    def list_all(self, limit: int = 100, offset: int = 0) -> JobListResponse:
        meta = self._read_meta()
        entries = sorted(meta.values(), key=lambda e: -e.get("created_at", 0))
        return JobListResponse(
            jobs=[JobResponse(**e) for e in entries[offset:offset+limit]],
            total=len(entries),
        )

    def cancel(self, job_id: str) -> bool:
        meta = self._read_meta()
        entry = meta.get(job_id)
        if not entry:
            return False
        if entry["status"] not in (JobStatus.QUEUED.value, JobStatus.TRAINING.value, JobStatus.VALIDATING.value):
            return False
        # Cancel on provider side
        prov = self._get_provider(FineTuneProvider(entry["provider"]))
        if prov.available and entry.get("provider_job_id"):
            try:
                prov.cancel_job(entry["provider_job_id"])
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        entry["status"] = JobStatus.CANCELLED.value
        entry["completed_at"] = _time.time()
        meta[job_id] = entry
        self._write_meta(meta)
        return True

    # ── Background execution ──────────────────────────────────────────

    async def _execute(self, job_id: str):
        """Run the full fine-tuning job lifecycle in background."""
        meta = self._read_meta()
        entry = meta.get(job_id)
        if not entry:
            return

        prov = self._get_provider(FineTuneProvider(entry["provider"]))

        try:
            # Step 1: Snapshot dataset
            entry["status"] = JobStatus.VALIDATING.value
            self._update(job_id, entry)
            snapshot_path = self._dataset_mgr.snapshot(entry["dataset_id"], job_id)

            # Step 2: Upload file
            entry["status"] = JobStatus.UPLOADING.value
            self._update(job_id, entry)
            file_id = await _asyncio.to_thread(prov.upload_file, str(snapshot_path))

            # Step 3: Create job
            entry["status"] = JobStatus.TRAINING.value
            entry["started_at"] = _time.time()
            suffix = entry["result_model"].split(":")[-1] if ":" in entry["result_model"] else entry["result_model"]
            result = await _asyncio.to_thread(
                prov.create_job,
                file_id=file_id,
                model=entry["base_model"],
                suffix=suffix,
                hyperparams=entry.get("hyperparams"),
            )
            entry["provider_job_id"] = result.provider_job_id
            self._update(job_id, entry)

            # Step 4: Poll until completion (with timeout)
            start_time = _time.time()
            while True:
                await _asyncio.sleep(30)  # Check every 30s
                result = await _asyncio.to_thread(prov.get_job, result.provider_job_id)
                new_status = _DS_STATUS_MAP.get(result.status, JobStatus.TRAINING)

                # Check timeout
                if _time.time() - start_time > _JOB_TIMEOUT_SECONDS:
                    entry["status"] = JobStatus.FAILED.value
                    entry["error"] = "Job timed out after 2 hours"
                    entry["completed_at"] = _time.time()
                    self._update(job_id, entry)
                    return

                if new_status.value != entry["status"]:
                    entry["status"] = new_status.value
                    self._update(job_id, entry)

                if new_status == JobStatus.COMPLETED:
                    entry["result_model"] = result.result_model or entry["result_model"]
                    entry["completed_at"] = _time.time()
                    self._update(job_id, entry)
                    # Register model with infra
                    await self._register_model(entry)
                    # Signal SFT completion for downstream RL pipeline
                    self._signal_sft_complete(entry)
                    return

                if new_status in (JobStatus.FAILED, JobStatus.CANCELLED):
                    entry["error"] = result.error
                    entry["completed_at"] = _time.time()
                    self._update(job_id, entry)
                    return

        except Exception as e:
            entry["status"] = JobStatus.FAILED.value
            entry["error"] = str(e)
            entry["completed_at"] = _time.time()
            self._update(job_id, entry)

    def _update(self, job_id: str, entry: dict):
        meta = self._read_meta()
        meta[job_id] = entry
        self._write_meta(meta)

    async def _register_model(self, entry: dict):
        """Register the fine-tuned model with infra ModelManager."""
        try:
            from infra.management.model.schemas import ModelInfo, ModelType, ModelSource, ModelConfig
            from infra.management.model.manager import ModelManager
            
            # Field integrity check before registration
            required = {"model_name": entry.get("result_model"), 
                       "base_model": entry.get("base_model"),
                       "provider": entry.get("provider")}
            missing = [f for f, v in required.items() if not v]
            if missing:
                logging.warning("Model registration aborted: missing fields %s", missing)
                # Degradation: write pending registration for admin recovery
                import json, time as _time2
                pending_path = os.path.join(os.path.expanduser("~/.aiplat"), "pending_models.json")
                pending = []
                if os.path.exists(pending_path):
                    try:
                        with open(pending_path) as f:
                            pending = json.load(f)
                    except Exception:
                        pass
                pending.append({"entry": entry, "missing": missing, "timestamp": _time2.time()})
                with open(pending_path, "w") as f:
                    json.dump(pending, f, indent=2, default=str)
                return
            
            mgr = ModelManager()
            await mgr.initialize()
            info = ModelInfo(
                id=f"ft:{entry['id']}",
                name=entry["result_model"],
                display_name=f"{entry['base_model']}:ft-{entry.get('dataset_name','')}",
                type=ModelType.CHAT,
                provider=entry["provider"],
                source=ModelSource.EXTERNAL,
                config=ModelConfig(api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com/v1"),
                description=f"Fine-tuned from {entry['base_model']} on {entry.get('dataset_name','')}",
                tags=["fine-tuned", entry["provider"]],
                capabilities=["chat", "function_call", "json_mode"],
            )
            await mgr.add_model(info)
            logging.info("Model registered: %s", info.name)
        except Exception as e:
            logging.warning("Model registration failed (non-critical): %s", str(e)[:200], exc_info=True)

    @staticmethod
    def _signal_sft_complete(entry: dict) -> None:
        """Write SFT completion signal for downstream RL pipeline.

        Saves {result_model, base_model, job_id, completed_at} to
        ~/.aiplat/sft_models/latest.json so RLTrainer can auto-detect
        the latest SFT model and start RL training on it.
        """
        try:
            signal_path = os.path.expanduser("~/.aiplat/sft_models/latest.json")
            os.makedirs(os.path.dirname(signal_path), exist_ok=True)
            signal = {
                "result_model": entry.get("result_model", ""),
                "base_model": entry.get("base_model", ""),
                "job_id": entry.get("id", ""),
                "dataset_id": entry.get("dataset_id", ""),
                "completed_at": _time.time(),
            }
            # Append to history log
            history_path = os.path.expanduser("~/.aiplat/sft_models/history.jsonl")
            os.makedirs(os.path.dirname(history_path), exist_ok=True)
            with open(history_path, "a") as f:
                f.write(json.dumps(signal) + "\n")
            # Write latest pointer
            with open(signal_path, "w") as f:
                json.dump(signal, f)
            logging.info("SFT→RL signal written: %s", signal["result_model"])
        except Exception:
            logging.debug("SFT→RL signal failed (non-critical)", exc_info=True)
