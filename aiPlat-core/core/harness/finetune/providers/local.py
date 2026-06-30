"""
LocalFineTuneProvider — local LoRA fine-tuning via MLX on Apple Silicon.

Implements the same interface as DeepSeekFineTuneProvider for plug-and-play
integration with the existing fine-tuning pipeline.
"""
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import FineTuneJobResult

_logger = logging.getLogger(__name__)


class LocalFineTuneProvider:
    """Local LoRA fine-tuning provider using MLX on Apple Silicon.
    
    Follows the same implicit interface as DeepSeekFineTuneProvider:
        available, display_name, supported_base_models
        check_quota(), estimate_cost(), upload_file(), create_job(), get_job(), cancel_job()
    """

    def __init__(self):
        self._jobs: Dict[str, dict] = {}  # in-memory job cache
        self._jobs_dir = self._resolve_jobs_dir()
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._trainers: Dict[str, Any] = {}  # MLXLoRATrainer instances
        self._load_jobs_meta()

    # ── Provider attributes ──

    @property
    def available(self) -> bool:
        """Check if local fine-tuning is available on this machine."""
        checks = []
        # 1. MLX installed
        try:
            import mlx  # noqa
            import mlx_lm  # noqa
            checks.append("mlx")
        except ImportError:
            return False

        # 2. Memory check
        try:
            import psutil
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            avail_gb = mem.available / (1024**3)
            swap_gb = swap.used / (1024**3)
            if avail_gb < 6.5:
                _logger.warning(f"LocalFineTune: only {avail_gb:.1f}GB available, need ≥6.5GB")
                return False
            if swap_gb > 2.0:
                _logger.warning(f"LocalFineTune: swap usage {swap_gb:.1f}GB > 2GB, please restart to free memory")
                return False
        except ImportError:
            pass  # psutil not installed, assume OK

        # 3. llama.cpp tools (for final GGUF export)
        from core.harness.finetune.gguf_exporter import GGUFExporter
        exporter = GGUFExporter()
        if not exporter.available:
            missing = exporter.get_missing_tools()
            _logger.warning(f"LocalFineTune: llama.cpp tools missing: {missing}")
            # Not blocking — training can proceed without export capability
        return True

    @property
    def display_name(self) -> str:
        return "本地 LoRA 微调 (MLX)"

    @property
    def supported_base_models(self) -> List[str]:
        """Get local Ollama models suitable for fine-tuning (≤13B)."""
        try:
            import urllib.request, json as _json
            r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
            data = json.loads(r.read())
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                # Filter: skip huge models, only include 7B- reference models
                size_gb = m.get("size", 0) / (1024**3)
                if size_gb < 20:  # <20GB on disk ≈ ≤13B params
                    models.append(name)
            return sorted(models)
        except Exception:
            # Fallback: return commonly available models for manual selection
            return ["qwen2.5-coder:7b", "qwen2.5:7b", "gemma4:12b", "llama3.2:3b"]

    def check_quota(self) -> Dict[str, int]:
        """Return quota info. Only one local job at a time."""
        active = sum(1 for j in self._jobs.values() if j.get("status") in ("TRAINING", "QUEUED", "UPLOADING"))
        return {"used": active, "total": 1}

    def estimate_cost(self, sample_count: int, epochs: int = 3) -> str:
        """Estimate training time (local = free)."""
        iters = sample_count * epochs
        est_sec = iters * 0.1  # ~10 tok/s → ~0.1s per iter for 1-sample batch
        if est_sec < 60:
            return f"免费 (本地计算) — 预计 {int(est_sec)} 秒"
        elif est_sec < 3600:
            return f"免费 (本地计算) — 预计 {int(est_sec/60)} 分钟"
        return f"免费 (本地计算) — 预计 {est_sec/3600:.1f} 小时"

    def upload_file(self, file_path: str) -> str:
        """Local 'upload' — just copy dataset to job workspace. Returns file_id."""
        # For local training, file_id = file_path (no actual upload)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Dataset not found: {file_path}")
        return file_path

    def create_job(self, file_id: str, model: str, suffix: str,
                   hyperparams: Optional[Dict[str, Any]] = None) -> FineTuneJobResult:
        """Create and start a local fine-tuning job."""
        from core.harness.finetune.mlx_trainer import MLXLoRATrainer

        hyperparams = hyperparams or {}
        template = hyperparams.get("template", "general")
        lora_rank = hyperparams.get("lora_rank", 0)
        lora_alpha = hyperparams.get("lora_alpha", 0)
        lr = hyperparams.get("lr", 0.0)
        iters = hyperparams.get("iters", 0)

        job_id = f"local-{_short_hash(model)}-{len(self._jobs)}"
        job_dir = self._jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Copy dataset to job workspace
        dataset_path = str(job_dir / "data.jsonl")
        if file_id != dataset_path:
            shutil.copy(file_id, dataset_path)

        # Convert model name to HF format
        hf_model = self._ollama_to_hf(model)

        # Create trainer
        trainer = MLXLoRATrainer(
            job_id=job_id,
            base_model=hf_model,
            dataset_path=dataset_path,
            output_dir=str(job_dir),
            template=template,
            lora_rank=lora_rank,
            lora_alpha=lora_alpha,
            lr=lr,
            iters=iters,
        )
        self._trainers[job_id] = trainer

        # Start training
        try:
            trainer.train()
        except RuntimeError as e:
            _logger.error(f"Local training start failed: {e}")
            return FineTuneJobResult(
                provider_job_id=job_id,
                result_model="",
                status="FAILED",
                error=str(e),
                training_tokens=0,
                estimated_cost_usd=0.0,
            )

        job_meta = {
            "job_id": job_id,
            "model": model,
            "hf_model": hf_model,
            "suffix": suffix,
            "template": template,
            "status": "TRAINING",
            "dataset_path": dataset_path,
            "created_at": __import__("time").time(),
        }
        self._jobs[job_id] = job_meta
        self._save_jobs_meta()

        return FineTuneJobResult(
            provider_job_id=job_id,
            result_model="",
            status="TRAINING",
            error="",
            training_tokens=0,
            estimated_cost_usd=0.0,
        )

    def get_job(self, provider_job_id: str) -> FineTuneJobResult:
        """Get job status including training progress."""
        job = self._jobs.get(provider_job_id)
        if not job:
            return FineTuneJobResult(
                provider_job_id=provider_job_id,
                result_model="",
                status="FAILED",
                error=f"Job not found: {provider_job_id}",
                training_tokens=0,
                estimated_cost_usd=0.0,
            )

        trainer = self._trainers.get(provider_job_id)
        if trainer and trainer.is_running:
            status = "TRAINING"
        elif trainer and trainer._process is not None and trainer._process.poll() == 0:
            status = "COMPLETED"
            job["status"] = "COMPLETED"
            self._save_jobs_meta()
            # Auto-export: fuse → gguf → register with Ollama
            if not job.get("_gguf_exported"):
                try:
                    _asyncio = __import__("asyncio")
                    _asyncio.ensure_future(self._auto_export_gguf(job, provider_job_id))
                    job["_gguf_exported"] = True
                    self._save_jobs_meta()
                except Exception:
                    pass
        elif trainer and trainer._process is not None and trainer._process.poll() is not None:
            status = "FAILED"
            job["status"] = "FAILED"
            self._save_jobs_meta()
        else:
            status = job.get("status", "QUEUED")

        # Build result model name if completed
        result_model = ""
        if status == "COMPLETED":
            suffix = job.get("suffix", "")
            base = job.get("model", "local")
            result_model = f"ft:{base}:{suffix}" if suffix else f"ft:{base}:{provider_job_id[:8]}"

        return FineTuneJobResult(
            provider_job_id=provider_job_id,
            result_model=result_model,
            status=status,
            error="",
            training_tokens=0,
            estimated_cost_usd=0.0,
        )

    def cancel_job(self, provider_job_id: str) -> bool:
        """Cancel a running training job."""
        trainer = self._trainers.get(provider_job_id)
        if trainer:
            return trainer.cancel()
        return False

    def get_progress(self, provider_job_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed training progress."""
        trainer = self._trainers.get(provider_job_id)
        if trainer:
            return trainer.progress
        return None

    # ── Internal helpers ──

    @staticmethod
    def _resolve_jobs_dir() -> Path:
        home = os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat"))
        return Path(home) / "finetune_jobs"

    @staticmethod
    def _ollama_to_hf(model_name: str) -> str:
        """Convert Ollama model name to HuggingFace format."""
        mapping = {
            "qwen2.5-coder:7b": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "qwen2.5-coder:14b": "Qwen/Qwen2.5-Coder-14B-Instruct",
            "qwen2.5:7b": "Qwen/Qwen2.5-7B-Instruct",
            "qwen2.5:14b": "Qwen/Qwen2.5-14B-Instruct",
            "gemma4:12b": "google/gemma-2-9b-it",
        }
        if model_name in mapping:
            return mapping[model_name]
        # Try to parse: "qwen2.5:7b" → "Qwen/Qwen2.5-7B-Instruct"
        if "qwen" in model_name.lower():
            return "Qwen/Qwen2.5-7B-Instruct"
        return model_name

    async def _auto_export_gguf(self, job: dict, provider_job_id: str):
        """Auto-chain: fuse adapters → convert to GGUF → register with Ollama."""
        try:
            from core.harness.finetune.gguf_exporter import GGUFExporter
            exporter = GGUFExporter()
            if not exporter.available:
                logging.warning("GGUF export skipped: llama.cpp tools not available")
                return

            base_model = job.get("model", "")
            suffix = job.get("suffix", "")
            model_name = f"{base_model}:{suffix}" if suffix else f"{base_model}:{provider_job_id[:8]}"

            # Step 1: Fuse LoRA adapters into base model
            adapter_path = self._jobs_dir / provider_job_id / "adapters"
            fused_output = self._jobs_dir / provider_job_id / "fused"
            await exporter.fuse_adapters(str(adapter_path), base_model, str(fused_output))

            # Step 2: Convert to GGUF (FP16 → Q4_K_M)
            gguf_path = self._jobs_dir / provider_job_id / f"{model_name.replace(':','-')}.gguf"
            await exporter.convert_to_gguf(str(fused_output), str(gguf_path))

            # Step 3: Register with Ollama
            await exporter.register_ollama(str(gguf_path), model_name.replace(":", "-"))

            job["gguf_path"] = str(gguf_path)
            logging.info("GGUF export complete: %s", gguf_path)
        except Exception as e:
            logging.warning("GGUF export failed (non-critical): %s", str(e)[:200], exc_info=True)

    def _save_jobs_meta(self):
        meta_path = self._jobs_dir / "jobs_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self._jobs, f, ensure_ascii=False, indent=2)

    def _load_jobs_meta(self):
        meta_path = self._jobs_dir / "jobs_meta.json"
        if meta_path.exists():
            try:
                self._jobs = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._jobs = {}


def _short_hash(s: str, length: int = 6) -> str:
    import hashlib
    return hashlib.md5(s.encode()).hexdigest()[:length]
