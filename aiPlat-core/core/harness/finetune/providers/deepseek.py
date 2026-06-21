"""
DeepSeek Fine-tuning Provider — 对接 DeepSeek API 的微调能力。

API 文档: https://api-docs.deepseek.com/api/create-fine-tuning-job

流程:
  1. POST /v1/files → 上传数据集
  2. POST /v1/fine_tuning/jobs → 创建微调作业
  3. GET /v1/fine_tuning/jobs/{id} → 轮询作业状态
  4. 完成后 model = "ft:deepseek-chat:{suffix}"
  5. 注册到 infra ModelManager
"""

from __future__ import annotations

import json as _json
import os as _os
import time as _time
from typing import Any, Dict, Optional

import httpx


# ── Provider API ────────────────────────────────────────────────────────

from . import FineTuneJobResult  # shared provider type


class DeepSeekFineTuneProvider:
    """DeepSeek fine-tuning API provider."""

    BASE_URL = "https://api.deepseek.com"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or _os.getenv("DEEPSEEK_API_KEY", "") or _os.getenv("AIPLAT_LLM_API_KEY", "")
        self._client = httpx.Client(base_url=self.BASE_URL, timeout=httpx.Timeout(60.0))

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    @property
    def display_name(self) -> str:
        return "DeepSeek"

    @property
    def supported_base_models(self) -> list:
        return ["deepseek-chat", "deepseek-v4-pro", "deepseek-v4-flash"]

    def check_quota(self) -> Dict[str, int]:
        """Check API quota by counting active jobs."""
        try:
            resp = self._client.get(
                "/v1/fine_tuning/jobs",
                params={"limit": 100},
                headers=self._headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("data", [])
                running = sum(1 for j in jobs if j.get("status") in ("running", "queued", "validating_files"))
                # DeepSeek allows up to 5 concurrent fine-tuning jobs (common limit)
                return {"total": 5, "used": running, "available": 5 - running}
        except Exception:
            pass
        return {"total": 0, "used": 0, "available": 0}

    def estimate_cost(self, sample_count: int, epochs: int = 3) -> str:
        """Estimate cost based on dataset size and training parameters.
        
        DeepSeek pricing (approximate): ~$0.25 per 1M training tokens.
        Typical conversation pair ≈ 500 tokens → sample_count × epochs × 500 ≈ total_tokens.
        """
        est_tokens = sample_count * epochs * 500
        est_cost = est_tokens / 1_000_000 * 0.25
        return f"~${est_cost:.2f}"

    # ── Fine-Tuning Job Lifecycle ──────────────────────────────────────

    def upload_file(self, file_path: str) -> str:
        """Upload a JSONL file for fine-tuning. Returns file_id."""
        with open(file_path, "rb") as f:
            resp = self._client.post(
                "/v1/files",
                files={"file": f, "purpose": (None, "fine-tune")},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        resp.raise_for_status()
        return resp.json()["id"]

    def create_job(
        self,
        file_id: str,
        model: str = "deepseek-chat",
        suffix: Optional[str] = None,
        hyperparams: Optional[Dict[str, Any]] = None,
    ) -> FineTuneJobResult:
        """Create a fine-tuning job. Returns job metadata."""
        body: Dict[str, Any] = {
            "model": model,
            "training_file": file_id,
        }
        if suffix:
            body["suffix"] = suffix
        if hyperparams:
            body["hyperparameters"] = hyperparams

        resp = self._client.post(
            "/v1/fine_tuning/jobs",
            json=body,
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        result = FineTuneJobResult()
        result.provider_job_id = data.get("id", "")
        result.status = data.get("status", "queued")
        result.result_model = data.get("fine_tuned_model", "")
        return result

    def get_job(self, provider_job_id: str) -> FineTuneJobResult:
        """Get fine-tuning job status."""
        resp = self._client.get(
            f"/v1/fine_tuning/jobs/{provider_job_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        result = FineTuneJobResult()
        result.provider_job_id = data.get("id", "")
        result.status = data.get("status", "queued")
        result.result_model = data.get("fine_tuned_model", "")
        result.error = str(data.get("error", "") or "")
        result.training_tokens = data.get("trained_tokens", 0) or 0
        return result

    def cancel_job(self, provider_job_id: str) -> bool:
        """Cancel a running fine-tuning job."""
        resp = self._client.post(
            f"/v1/fine_tuning/jobs/{provider_job_id}/cancel",
            headers=self._headers(),
        )
        return resp.status_code == 200

    # ── Helpers ────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
