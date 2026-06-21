"""
MLX LoRA Trainer — local fine-tuning on Apple Silicon via MLX.

Uses mlx_lm.lora for QLoRA-style 4-bit training with MPS backend.
"""
import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)

# ── Default LoRA hyperparams per template ──
_DEFAULT_HYPERPARAMS = {
    "general":          {"rank": 16, "alpha": 32, "iters": 200, "lr": 1e-4, "batch": 1},
    "code":             {"rank": 32, "alpha": 64, "iters": 300, "lr": 5e-5, "batch": 1},
    "customer_service": {"rank": 8,  "alpha": 16, "iters": 100, "lr": 2e-4, "batch": 1},
    "custom":           {"rank": 16, "alpha": 32, "iters": 200, "lr": 1e-4, "batch": 1},
}


class MLXLoRATrainer:
    """Manage MLX LoRA training lifecycle — spawn subprocess, track progress."""

    def __init__(self, job_id: str, base_model: str, dataset_path: str,
                 output_dir: str, *,
                 template: str = "general",
                 lora_rank: int = 0,
                 lora_alpha: int = 0,
                 lr: float = 0.0,
                 iters: int = 0):
        self.job_id = job_id
        self.base_model = base_model        # e.g., "qwen/Qwen2.5-7B-Instruct"
        self.dataset_path = dataset_path    # ShareGPT JSON
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        hp = dict(_DEFAULT_HYPERPARAMS.get(template, _DEFAULT_HYPERPARAMS["general"]))
        self.lora_rank = lora_rank or hp["rank"]
        self.lora_alpha = lora_alpha or hp["alpha"]
        self.lr = lr or hp["lr"]
        self.iters = iters or hp["iters"]
        self.batch_size = hp["batch"]

        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._progress_file = self.output_dir / "progress.json"
        self._train_log = self.output_dir / "train.log"
        self._adapter_path = self.output_dir / "adapters.safetensors"

    # ── Public API ──

    @property
    def available(self) -> bool:
        """Check if MLX LoRA training is available."""
        try:
            import mlx  # noqa
            import mlx_lm  # noqa
            return True
        except ImportError:
            return False

    @staticmethod
    def check_environment() -> dict:
        """Return environment check results."""
        checks = {"mlx": False, "mlx_lm": False, "memory_gb": 0.0, "swap_gb": 0.0, "ok": False}
        try:
            import mlx; checks["mlx"] = True  # noqa
            import mlx_lm; checks["mlx_lm"] = True  # noqa
        except ImportError:
            return checks

        # Memory check (macOS)
        try:
            import psutil
            mem = psutil.virtual_memory()
            checks["memory_gb"] = round(mem.available / (1024**3), 1)
            swap = psutil.swap_memory()
            checks["swap_gb"] = round(swap.used / (1024**3), 1)
        except ImportError:
            # Fallback: vm_stat
            checks["memory_gb"] = 8.0  # assume OK

        checks["ok"] = checks["mlx"] and checks["mlx_lm"] and checks["memory_gb"] >= 6.5
        return checks

    @staticmethod
    def convert_dataset(jsonl_path: str) -> Optional[str]:
        """Convert JSONL Chat format → ShareGPT format for MLX.
        
        Input (JSONL): {"messages": [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]}
        Output (ShareGPT): [{"conversations": [{"from":"human","value":"..."}, {"from":"gpt","value":"..."}]}]
        
        Returns path to converted file or None.
        """
        jsonl_path = Path(jsonl_path)
        if not jsonl_path.exists():
            _logger.error(f"Dataset not found: {jsonl_path}")
            return None

        conversations = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    _logger.warning(f"Line {line_num}: invalid JSON, skipping")
                    continue

                msgs = record.get("messages", [])
                if len(msgs) < 2:
                    _logger.warning(f"Line {line_num}: <2 messages, skipping")
                    continue

                turns = []
                for msg in msgs:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        turns.append({"from": "human", "value": content})
                    elif role == "assistant":
                        turns.append({"from": "gpt", "value": content})
                    elif role == "system":
                        turns.append({"from": "system", "value": content})
                    else:
                        turns.append({"from": role, "value": content})

                if turns:
                    conversations.append({"conversations": turns})

        if len(conversations) < 10:
            _logger.warning(f"Only {len(conversations)} valid samples (<10), training may fail")

        output_path = jsonl_path.parent / f"{jsonl_path.stem}_sharegpt.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(conversations, f, ensure_ascii=False, indent=2)

        _logger.info(f"Converted {len(conversations)} samples → {output_path}")
        return str(output_path)

    def train(self) -> subprocess.Popen:
        """Start MLX LoRA training as subprocess. Non-blocking — returns immediately."""
        if not self.available:
            raise RuntimeError("MLX/mlx_lm not installed")

        sharegpt_path = self.convert_dataset(self.dataset_path)
        if not sharegpt_path:
            raise RuntimeError("Dataset conversion failed")

        cmd = [
            "python", "-m", "mlx_lm.lora",
            "--model", self.base_model,
            "--data", sharegpt_path,
            "--train",
            "--lora-layers", str(self.lora_rank),
            "--batch-size", str(self.batch_size),
            "--iters", str(self.iters),
            "--learning-rate", str(self.lr),
            "--grad-checkpoint",
            "--save-every", "50",
            "--adapter-path", str(self._adapter_path),
        ]

        _logger.info(f"Starting MLX training: {' '.join(cmd)}")
        self._stop_event.clear()

        log_fh = open(self._train_log, "w", encoding="utf-8")
        self._process = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        # Start progress monitor in background thread
        threading.Thread(target=self._monitor_progress, daemon=True).start()

        return self._process

    def cancel(self) -> bool:
        """Signal training to stop gracefully."""
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            return True
        return False

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def progress(self) -> Dict[str, Any]:
        """Read latest training progress from file."""
        if self._progress_file.exists():
            try:
                return json.loads(self._progress_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "current_iter": 0,
            "total_iters": self.iters,
            "loss": None,
            "tokens_per_sec": 0.0,
            "elapsed_sec": 0,
            "estimated_remaining_sec": 0,
            "status": "idle",
        }

    @property
    def adapter_path(self) -> str:
        return str(self._adapter_path)

    # ── Internal ──

    def _monitor_progress(self):
        """Background thread: parse train.log for loss/iter and write progress.json."""
        last_write = 0.0
        while not self._stop_event.is_set():
            if self._process is None or self._process.poll() is not None:
                break
            if not self._train_log.exists():
                time.sleep(2)
                continue

            try:
                text = self._train_log.read_text(encoding="utf-8")
            except OSError:
                time.sleep(2)
                continue

            progress = self._parse_progress(text)
            if progress:
                now = time.time()
                if now - last_write >= 3:  # write every 3s to reduce I/O
                    self._progress_file.write_text(
                        json.dumps(progress, ensure_ascii=False), encoding="utf-8")
                    last_write = now

            time.sleep(2)

        # Final write
        if self._process is not None:
            returncode = self._process.poll()
            status = "completed" if returncode == 0 else "failed"
            self._progress_file.write_text(
                json.dumps({"status": status, "current_iter": self.iters, "total_iters": self.iters},
                           ensure_ascii=False), encoding="utf-8")

    def _parse_progress(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse MLX training output for progress metrics."""
        # Pattern: "Iter 50: Train loss 1.234, It/sec 0.456, Tokens/sec 150.789"
        match = re.search(
            r"Iter\s+(\d+):\s+Train loss\s+([\d.]+).*?Tokens/sec\s+([\d.]+)",
            text, re.IGNORECASE)
        if not match:
            return None

        current = int(match.group(1))
        loss = float(match.group(2))
        tok_s = float(match.group(3))

        elapsed = 0.0
        t_match = re.search(r"Training time.*?([\d.]+)s", text)
        if t_match:
            elapsed = float(t_match.group(1))

        remaining = 0.0
        if current > 0 and self.iters > current:
            rate = current / max(elapsed, 0.1)
            remaining = (self.iters - current) / rate if rate > 0 else 0

        return {
            "current_iter": current,
            "total_iters": self.iters,
            "loss": loss,
            "tokens_per_sec": tok_s,
            "elapsed_sec": round(elapsed, 1),
            "estimated_remaining_sec": round(remaining, 0),
            "status": "training",
        }
