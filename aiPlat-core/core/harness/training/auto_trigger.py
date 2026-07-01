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
# disposition: internal data type — Phase 4.3 SFT auto-trigger, wiring pending
class SFTDatasetConfig:
    min_quality_label: str = "positive"
    max_samples: int = 1000
    output_format: str = "sharegpt"  # sharegpt / alpaca / openai
    target_model: str = "qwen2.5-coder:7b"  # noqa: env-legacy — SFT dataset default, not engine routing


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
        """生成 SFT 数据集 + 分层训练/验证分割 + 自动提交训练 Job"""
        # 1. 获取高质量样本 (already filtered by TrajectoryScorer in _fetch_samples)
        samples = await self._fetch_samples(limit=self._max_samples)

        if not samples:
            _log.warning("SFT AutoTrigger: no qualified samples found")
            return

        # 1.5 Paper Data Recipes: learnability filter (student model must be able to imitate)
        student_model = os.getenv("AIPLAT_SFT_STUDENT_MODEL", "")  # noqa: env-legacy — training config
        teacher_model = os.getenv("AIPLAT_SFT_TEACHER_MODEL", "")  # noqa: env-legacy — training config
        if student_model and samples:
            try:
                from core.harness.training.trajectory_scorer import TrajectoryScorer
                scorer = TrajectoryScorer()
                learnable = []
                for s in samples:
                    run_id = s.get("run_id", "")
                    if not run_id or await scorer.is_learnable(run_id, student_model):
                        learnable.append(s)
                if learnable:
                    samples = learnable
                    _log.info("Learnability filter: %d/%d samples pass", len(learnable), len(samples) if 'len' in dir() else 0)
            except Exception:
                _log.debug("Learnability filter skipped", exc_info=True)

        # 2. 生成 ShareGPT 格式
        dataset = self._convert_to_sharegpt(samples)
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # 3. 分层训练/验证分割 (15% val, stratify by task_type)
        train_items, val_items = self._split_train_val(dataset, samples, val_ratio=0.15)
        
        train_path = os.path.join(self._dataset_dir, f"sft_train_{timestamp}.jsonl")
        val_path = os.path.join(self._dataset_dir, f"sft_val_{timestamp}.jsonl")
        os.makedirs(self._dataset_dir, exist_ok=True)
        
        with open(train_path, "w", encoding="utf-8") as f:
            for item in train_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        if val_items:
            with open(val_path, "w", encoding="utf-8") as f:
                for item in val_items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

        # 4. 自动提交训练 Job (不再仅发通知)
        job_id = await self._auto_submit_job(train_path, val_path, timestamp)

        # 5. 推送通知
        await self._notify(train_path, len(train_items), job_id, val_path, len(val_items))

        # 6. 重置计数
        self._quality_count = 0
        _log.info("SFT AutoTrigger: train=%d, val=%d, job=%s", len(train_items), len(val_items), job_id or "skipped")

    def _split_train_val(self, dataset: list, samples: list, val_ratio: float = 0.15):
        """分层分割：按 task_type 分层，防止分布偏移。"""
        if len(dataset) < 10:
            return dataset, []
        try:
            from sklearn.model_selection import train_test_split
            task_types = [s.get("task_type", s.get("run_id", "default")) for s in samples]
            train_idx, val_idx = train_test_split(
                range(len(dataset)), test_size=val_ratio,
                stratify=task_types, random_state=42,
            )
            train = [dataset[i] for i in train_idx]
            val = [dataset[i] for i in val_idx]
            return train, val
        except ImportError:
            # Fallback: simple random split without stratification
            import random
            random.seed(42)
            n_val = max(1, int(len(dataset) * val_ratio))
            indices = list(range(len(dataset)))
            random.shuffle(indices)
            return [dataset[i] for i in indices[n_val:]], [dataset[i] for i in indices[:n_val]]

    async def _auto_submit_job(self, train_path: str, val_path: str, timestamp: str) -> Optional[str]:
        """自动导入数据集并提交训练 Job"""
        try:
            from core.harness.finetune.job_manager import JobManager
            from core.schemas_finetune import JobCreateRequest, FineTuneProvider, FineTuneTemplate
            
            mgr = JobManager()
            provider = os.getenv("AIPLAT_SFT_PROVIDER", "local")
            base_model = os.getenv("AIPLAT_SFT_BASE_MODEL", "qwen2.5-coder:7b")  # noqa: env-legacy — training config
            
            # Step 1: Import dataset via DatasetManager
            import_result = await mgr._dataset_mgr.import_jsonl(
                name=f"sft-{timestamp}",
                file_path=train_path,
                description=f"Auto-generated SFT dataset ({timestamp})",
            )
            dataset_id = import_result.id if hasattr(import_result, 'id') else import_result.get("id", "")
            
            # Step 2: Create training job
            req = JobCreateRequest(
                base_model=base_model,
                dataset_id=dataset_id,
                provider=FineTuneProvider(provider),
                template=FineTuneTemplate.GENERAL,
                hyperparams={"epochs": 3, "learning_rate_multiplier": 1.0},
            )
            resp = mgr.create(req)
            return resp.id
        except Exception:
            _log.debug("Auto job submission skipped (manual trigger required)", exc_info=True)
            return None

    def get_status(self) -> Dict[str, Any]:
        """Operational monitoring: accumulated sample counts and threshold info."""
        return {
            "enabled": self._enabled,
            "approved_total": self._approved_count,
            "quality_count": self._quality_count,
            "threshold": self._threshold,
            "quality_threshold": self._quality_threshold,
            "max_samples": self._max_samples,
            "progress_pct": round(self._quality_count / self._threshold * 100, 1) if self._threshold > 0 else 0.0,
            "ready_to_trigger": self._quality_count >= self._threshold,
            "dataset_dir": self._dataset_dir,
        }

    async def _fetch_samples(self, limit: int) -> List[Dict[str, Any]]:
        """从 execution_store 获取标记为 'positive' 的样本，经轨迹评分过滤 + 混合采样"""
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            # Fetch more samples than needed to allow scoring-based filtering
            fetch_limit = max(limit * 3, 2000)
            results = await store.query_meta(key="implicit_label", value="positive", limit=fetch_limit)
            samples = list(results) if isinstance(results, list) else results.get("items", [])

            # OpenThoughts-Agent style: score trajectories and keep only high-quality
            if samples:
                from core.harness.training.trajectory_scorer import TrajectoryScorer
                scorer = TrajectoryScorer()
                run_ids = [s.get("run_id", "") for s in samples if s.get("run_id")]
                if run_ids:
                    scores = await scorer.score_batch(run_ids)
                    scored = [(s, scores.get(s.get("run_id", ""), 0.0)) for s in samples]
                    # Keep only samples with score > 0.5
                    filtered = [(s, sc) for s, sc in scored if sc > 0.5]
                    filtered.sort(key=lambda x: x[1], reverse=True)
                    
                    # Paper Data Recipes: mixed sampling by task_type (Top-4 sources)
                    samples = self._mixed_sample_by_task_type(filtered, limit)
            return samples
        except Exception:
            return []

    def _mixed_sample_by_task_type(
        self, scored: List[tuple], limit: int
    ) -> List[Dict[str, Any]]:
        """混合采样：按 task_type 分组均匀采样 Top 来源，避免单一来源主导"""
        buckets: Dict[str, List[tuple]] = {}
        for s, sc in scored:
            tt = s.get("task_type", "general")
            buckets.setdefault(tt, []).append((s, sc))
        
        source_order = ["coding", "terminal", "qa", "system", "general"]
        selected = []
        source_idx = 0
        while len(selected) < limit and buckets:
            source = source_order[source_idx % len(source_order)]
            bucket = buckets.get(source)
            if bucket:
                selected.append(bucket.pop(0)[0])
                if not bucket:
                    del buckets[source]
            source_idx += 1
            # If all buckets exhausted, take remaining from any source
            if not any(buckets.values()):
                break
        
        # Pad with any remaining if mixed sampling undershoots limit
        remaining = [s for bucket in buckets.values() for s, _ in bucket]
        selected.extend(remaining[:limit - len(selected)])
        return selected[:limit]

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

    async def _notify(self, dataset_path: str, sample_count: int, job_id: str = "", val_path: str = "", val_count: int = 0):
        """推送管理端通知"""
        try:
            from core.harness.observation.event_bus import EventBus
            body = f"已积累 {sample_count} 条训练样本 (验证集: {val_count} 条)"
            if job_id:
                body += f", 训练 Job 已自动提交: {job_id}"
            EventBus.publish("sft_dataset_ready", {
                "type": "sft_trigger",
                "title": "建议启动 LoRA 微调",
                "body": body,
                "dataset_path": dataset_path,
                "val_path": val_path,
                "sample_count": sample_count,
                "val_count": val_count,
                "job_id": job_id,
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
