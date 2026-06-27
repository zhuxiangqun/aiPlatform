"""
LoRA AutoTrigger — 自动微调触发 (Phase 4.3)

监听 AutoLearner 审批通过的高质量 Skill，累计 ≥ 阈值时自动生成 SFT 数据集，
通知管理员启动 LoRA 微调。

环境变量:
  AIPLAT_SFT_AUTO_TRIGGER_THRESHOLD  — 触发阈值 (默认: 100)
  AIPLAT_SFT_MIN_QUALITY              — 最低质量阈值 (默认: 0.8)
  AIPLAT_SFT_MAX_SAMPLES              — 最大样本数 (默认: 1000)
  AIPLAT_SFT_ENABLED                  — 是否启用 (默认: true)
"""

from __future__ import annotations
import logging

import asyncio, json, os, time, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.sft_trigger")


@dataclass
class SFTDatasetConfig:
    min_quality_label: str = "positive"
    max_samples: int = 1000
    output_format: str = "sharegpt"  # sharegpt / alpaca / openai
    target_model: str = "qwen2.5-coder:7b"


class LoRAAutoTrigger:
    """监听 AutoLearner 审批事件，自动触发微调建议。

    Usage:
        trigger = LoRAAutoTrigger()
        await trigger.on_skill_approved(skill_draft)

        # 周期性检查
        await trigger.check_and_trigger()
    """

    def __init__(self):
        self._approved_count = 0
        self._quality_count = 0   # 仅计高质量 (confidence ≥ threshold)
        self._threshold = int(os.getenv("AIPLAT_SFT_AUTO_TRIGGER_THRESHOLD", "100"))
        self._quality_threshold = float(os.getenv("AIPLAT_SFT_MIN_QUALITY", "0.8"))
        self._max_samples = int(os.getenv("AIPLAT_SFT_MAX_SAMPLES", "1000"))
        self._enabled = os.getenv("AIPLAT_SFT_ENABLED", "true").lower() not in ("0", "false", "no")
        self._dataset_dir = os.path.expanduser("~/.aiplat/training")
        os.makedirs(self._dataset_dir, exist_ok=True)

    async def on_skill_approved(self, skill_draft: Any):
        """AutoLearner 审批通过的回调"""
        if not self._enabled:
            return

        self._approved_count += 1
        confidence = getattr(skill_draft, "confidence", 0.0)
        if confidence >= self._quality_threshold:
            self._quality_count += 1

        if self._quality_count >= self._threshold:
            await self.trigger()

    async def trigger(self):
        """生成 SFT 数据集 + 推送通知"""
        # 1. 获取高质量样本
        samples = await self._fetch_samples(limit=self._max_samples)

        if not samples:
            _log.warning("SFT AutoTrigger: no qualified samples found")
            return

        # 2. 生成 ShareGPT 格式
        dataset = self._convert_to_sharegpt(samples)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self._dataset_dir, f"sft_dataset_{timestamp}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for item in dataset:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        # 3. 推送通知
        await self._notify(path, len(dataset))

        # 4. 重置计数
        self._quality_count = 0
        _log.info(f"SFT AutoTrigger: dataset generated at {path} ({len(dataset)} samples)")

    async def _fetch_samples(self, limit: int) -> List[Dict[str, Any]]:
        """从 execution_store 获取标记为 'positive' 的样本"""
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            # Query meta table for implicit_label=positive
            results = await store.query_meta(key="implicit_label", value="positive", limit=limit)
            return results if isinstance(results, list) else results.get("items", [])
        except Exception:
            return []

    def _convert_to_sharegpt(self, samples: list) -> list:
        """转换为 ShareGPT 格式"""
        return [
            {
                "conversations": [
                    {"from": "human", "value": s.get("user_input", "") or s.get("question", "") or ""},
                    {"from": "gpt", "value": s.get("assistant_output", "") or s.get("answer", "") or ""},
                ]
            }
            for s in samples
            if s.get("user_input") or s.get("question")
        ]

    async def _notify(self, dataset_path: str, sample_count: int):
        """推送管理端通知"""
        try:
            from core.harness.observation.event_bus import EventBus
            EventBus.publish("sft_dataset_ready", {
                "type": "sft_trigger",
                "title": "建议启动 LoRA 微调",
                "body": f"已积累 {sample_count} 条高质量 Skill 样本, 数据集: {dataset_path}",
                "dataset_path": dataset_path,
                "sample_count": sample_count,
                "action": "/infra/finetune/new",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "approved_count": self._approved_count,
            "quality_count": self._quality_count,
            "threshold": self._threshold,
            "quality_min": self._quality_threshold,
            "enabled": self._enabled,
            "next_trigger_at": max(0, self._threshold - self._quality_count),
        }


# ── Global singleton ─────────────────────────────────────────────────────────

_trigger: Optional[LoRAAutoTrigger] = None

def get_lora_auto_trigger() -> LoRAAutoTrigger:
    global _trigger
    if _trigger is None:
        _trigger = LoRAAutoTrigger()
    return _trigger
