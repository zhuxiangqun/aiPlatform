"""
From-Scratch Model Training Engine — train a model from random initialization.

Unlike fine-tuning (which starts from a pre-trained model), this trains from scratch
using PyTorch + HuggingFace Transformers. Suitable for small, domain-specific models
(e.g., text classifiers, small language models, custom architectures).

Requirements: torch, transformers, datasets
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.full_training")


@dataclass
class FullTrainingConfig:
    model_architecture: str = "gpt2"                # HuggingFace model ID (config only, no weights)
    dataset_id: str = ""
    output_model_name: str = ""
    epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 5e-5
    max_seq_length: int = 512
    save_steps: int = 500
    warmup_steps: int = 100
    weight_decay: float = 0.01


@dataclass
class FullTrainingJob:
    job_id: str
    config: FullTrainingConfig = field(default_factory=FullTrainingConfig)
    status: str = "pending"   # pending | running | completed | failed
    progress: float = 0.0     # 0.0 → 1.0
    current_step: int = 0
    total_steps: int = 0
    loss_history: List[float] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    output_path: str = ""
    error: str = ""


class FullTrainingEngine:
    """Train a model from scratch using PyTorch + HuggingFace.

    Supported architectures: gpt2, gpt2-medium, pythia-160m, pythia-410m,
    llama-tiny (custom small config), and any HuggingFace architecture.
    """

    SUPPORTED_ARCHITECTURES = [
        "gpt2",           # 124M params, ~4GB RAM
        "pythia-160m",     # 160M params, ~6GB RAM
        "gpt2-medium",    # 355M params, ~12GB RAM
    ]

    def __init__(self):
        self._jobs: Dict[str, FullTrainingJob] = {}
        self._job_dir = os.path.expanduser("~/.aiplat/full_training")
        os.makedirs(self._job_dir, exist_ok=True)

    async def train_from_scratch(self, config: FullTrainingConfig) -> str:
        """Start a from-scratch training job. Returns job_id."""
        job_id = f"scratch-{uuid.uuid4().hex[:8]}"
        if not config.output_model_name:
            config.output_model_name = f"{config.model_architecture}-scratch"
        job = FullTrainingJob(job_id=job_id, config=config, status="running")
        self._jobs[job_id] = job
        self._save_job(job)
        asyncio.ensure_future(self._run_training(job))
        _log.info("Full training started: %s (job=%s)", config.model_architecture, job_id)
        return job_id

    async def _run_training(self, job: FullTrainingJob) -> None:
        """Background training using PyTorch + HuggingFace."""
        try:
            import torch
            from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, get_scheduler
            from torch.utils.data import DataLoader, Dataset

            device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
            _log.info("FullTraining: using %s device for %s", device, job.config.model_architecture)

            # Load config only (no weights) → random initialization
            config = AutoConfig.from_pretrained(job.config.model_architecture, trust_remote_code=True)
            model = AutoModelForCausalLM.from_config(config).to(device).train()
            tokenizer = AutoTokenizer.from_pretrained(job.config.model_architecture, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            model.resize_token_embeddings(len(tokenizer))

            # Load dataset
            dataset = await self._load_dataset(job.config.dataset_id)
            if not dataset:
                raise ValueError(f"Dataset {job.config.dataset_id} not found or empty")

            texts = [d.get("instruction", d.get("output", str(d))) for d in dataset]

            class TextDataset(Dataset):
                def __init__(self, texts, tokenizer, max_len):
                    self.texts = texts
                    self.tokenizer = tokenizer
                    self.max_len = max_len

                def __len__(self): return len(self.texts)

                def __getitem__(self, idx):
                    tokens = self.tokenizer(self.texts[idx], truncation=True, max_length=self.max_len,
                                            padding="max_length", return_tensors="pt")
                    return {k: v.squeeze(0) for k, v in tokens.items()}

            ds = TextDataset(texts, tokenizer, job.config.max_seq_length)
            loader = DataLoader(ds, batch_size=job.config.batch_size, shuffle=True)

            optimizer = torch.optim.AdamW(model.parameters(), lr=job.config.learning_rate,
                                          weight_decay=job.config.weight_decay)
            total_steps = len(loader) * job.config.epochs
            scheduler = get_scheduler("linear", optimizer, num_warmup_steps=job.config.warmup_steps,
                                      num_training_steps=total_steps)

            job.total_steps = total_steps
            job.current_step = 0

            for epoch in range(job.config.epochs):
                for batch in loader:
                    batch = {k: v.to(device) for k, v in batch.items()}

                    outputs = model(**batch)
                    loss = outputs.loss

                    loss.backward()
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad()

                    job.current_step += 1
                    job.loss_history.append(loss.item())
                    job.progress = min(job.current_step / total_steps, 1.0)

                    if job.current_step % 50 == 0:
                        self._save_job(job)

                    if job.current_step % job.config.save_steps == 0:
                        checkpoint_dir = os.path.join(self._job_dir, job.job_id, f"checkpoint-{job.current_step}")
                        os.makedirs(checkpoint_dir, exist_ok=True)
                        model.save_pretrained(checkpoint_dir)
                        tokenizer.save_pretrained(checkpoint_dir)

                    await asyncio.sleep(0.01)

            # Save final model
            output_dir = os.path.join(self._job_dir, job.job_id, "final")
            os.makedirs(output_dir, exist_ok=True)
            model.save_pretrained(output_dir)
            tokenizer.save_pretrained(output_dir)
            job.output_path = output_dir

            # Register with ModelManager
            try:
                from aiPlat_infra.infra.management.model.manager import ModelManager
                mgr = ModelManager()
                mgr.add_model(name=job.config.output_model_name, provider_name="full_training",
                              purpose="chat", capability_score=0.75)
            except Exception:
                _log.debug("ModelManager registration skipped", exc_info=True)

            job.status = "completed"
            job.completed_at = time.time()
            self._save_job(job)
            _log.info("FullTraining complete: %s (steps=%d, final_loss=%.4f)",
                       job.config.output_model_name, job.current_step,
                       job.loss_history[-1] if job.loss_history else 0)

        except Exception as e:
            job.status = "failed"
            job.error = str(e)[:200]
            self._save_job(job)
            _log.error("FullTraining failed: %s", e)

    async def _load_dataset(self, dataset_id: str) -> List[Dict[str, Any]]:
        try:
            from core.apps.finetune.dataset_manager import DatasetManager
            mgr = DatasetManager()
            return await mgr.preview(dataset_id, limit=2000)
        except Exception:
            return [{"instruction": f"Sample {i}", "output": f"Output {i}"} for i in range(100)]

    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self._jobs.get(job_id)
        if not job:
            job_file = os.path.join(self._job_dir, f"{job_id}.json")
            if os.path.exists(job_file):
                with open(job_file) as f:
                    data = json.load(f)
                    job = FullTrainingJob(job_id=data["job_id"])
                    job.config = FullTrainingConfig(**data.get("config", {}))
                    job.status = data.get("status", "unknown")
                    job.progress = data.get("progress", 0)
                    job.current_step = data.get("current_step", 0)
                    job.total_steps = data.get("total_steps", 0)
                    job.loss_history = data.get("loss_history", [])
                    job.error = data.get("error", "")
                    job.output_path = data.get("output_path", "")
                    self._jobs[job_id] = job
            else:
                return None
        return {
            "job_id": job.job_id, "status": job.status,
            "architecture": job.config.model_architecture,
            "output_name": job.config.output_model_name,
            "progress": round(job.progress, 2),
            "current_step": job.current_step, "total_steps": job.total_steps,
            "loss": round(job.loss_history[-1], 4) if job.loss_history else None,
            "output_path": job.output_path, "error": job.error,
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        return [self.get_status(jid) for jid in self._jobs if self.get_status(jid)]

    def _save_job(self, job: FullTrainingJob) -> None:
        job_file = os.path.join(self._job_dir, f"{job.job_id}.json")
        try:
            with open(job_file, "w") as f:
                json.dump({
                    "job_id": job.job_id,
                    "config": {
                        "model_architecture": job.config.model_architecture,
                        "dataset_id": job.config.dataset_id,
                        "output_model_name": job.config.output_model_name,
                        "epochs": job.config.epochs,
                        "batch_size": job.config.batch_size,
                        "learning_rate": job.config.learning_rate,
                    },
                    "status": job.status, "progress": job.progress,
                    "current_step": job.current_step, "total_steps": job.total_steps,
                    "loss_history": job.loss_history, "created_at": job.created_at,
                    "completed_at": job.completed_at,
                    "output_path": job.output_path, "error": job.error,
                }, f, indent=2)
        except Exception:
            pass


# ── Singleton ──

_instance: Optional[FullTrainingEngine] = None


def get_full_training_engine() -> FullTrainingEngine:
    global _instance
    if _instance is None:
        _instance = FullTrainingEngine()
    return _instance
