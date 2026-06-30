"""
ImplicitFeedback — 用户行为隐式反馈收集器 (Phase 4.2)

从用户行为中提取隐式反馈信号:
  • 复制答案 → 正向信号 (+0.3)
  • 追问/缩小问题 → 负向信号 (-0.1)
  • 30s 无操作 → 微弱负向 (-0.05)

聚合后:
  1. 调整 ProvenanceTracker 权重
  2. 标记 execution_store 元数据为 AutoLearner 正/负样本
"""

from __future__ import annotations
import logging

import asyncio, os, time, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.implicit_feedback")


@dataclass
# disposition: internal data type — used by ImplicitFeedbackCollector; wired from agents.py
class ImplicitSignal:
    run_id: str
    signal_type: str     # copy_full / select_text / re_query / abandon / repeat_query
    value: float = 1.0   # 信号强度 [-0.5, +0.5]
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)


# ── Signal weights ─────────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    "copy_full":      0.30,   # 用户复制全文 → 高质量
    "select_text":     0.15,   # 用户选中片段 → 部分有用
    "re_query":       -0.10,  # 用户追问 → 前次答案不完整
    "repeat_query":   -0.20,  # 重复相同问题 → 前次答案无效
    "abandon":        -0.05,  # 30s 无操作 → 可能不满意
}

# ── Thresholds ──────────────────────────────────────────────────────────

FLUSH_SIZE = 10             # 每 10 个信号聚合一次
POSITIVE_THRESHOLD = 3      # 累积 ≥ 3 正向 → 标记正样本
NEGATIVE_THRESHOLD = 3      # 累积 ≥ 3 负向 → 标记负样本


# disposition: internal class — wired from agents.py:382-383,676-677,704-705
class ImplicitFeedbackCollector:
    """隐式反馈收集器 — 批量聚合 + 多目标权重自适应 (EMA 平滑)"""

    def __init__(self):
        self._buffer: List[ImplicitSignal] = []
        self._run_signals: Dict[str, List[ImplicitSignal]] = {}  # run_id → signals
        self._enabled = os.getenv("AIPLAT_IMPLICIT_FEEDBACK_ENABLED", "true").lower() not in ("0", "false", "no")

        # Phase 2 (P1): Multi-objective reward weights with EMA smoothing
        self._objective_weights = {"accuracy": 0.5, "speed": 0.3, "conciseness": 0.2}
        self._ema_alpha = float(os.getenv("AIPLAT_REWARD_EMA_ALPHA", "0.1"))  # [0, 1], smaller = smoother
        self._sample_count = 0
        self._adjust_interval = int(os.getenv("AIPLAT_REWARD_ADJUST_INTERVAL", "20"))

    async def record(
        self,
        *,
        run_id: str,
        signal_type: str,
        value: float = 0.0,
        session_id: str = "",
    ):
        """记录单个隐式反馈信号"""
        if not self._enabled or not run_id:
            return

        weight = value or SIGNAL_WEIGHTS.get(signal_type, 0.0)
        if abs(weight) < 0.01:
            return

        signal = ImplicitSignal(
            run_id=run_id,
            signal_type=signal_type,
            value=weight,
            session_id=session_id,
        )
        self._buffer.append(signal)

        # Group by run_id
        if run_id not in self._run_signals:
            self._run_signals[run_id] = []
        self._run_signals[run_id].append(signal)

        # Count signals for periodic weight adjustment
        self._sample_count += 1

        # Flush when buffer is full
        if len(self._buffer) >= FLUSH_SIZE:
            await self._flush()

        # Periodic multi-objective weight adjustment (EMA smoothed)
        if self._sample_count % self._adjust_interval == 0:
            self._adjust_weights()

    async def _flush(self):
        """批量聚合信号 → 调整权重 + 标记样本"""
        for run_id, signals in list(self._run_signals.items()):
            total_score = sum(s.value for s in signals)
            positive = sum(1 for s in signals if s.value > 0)
            negative = sum(1 for s in signals if s.value < 0)

            # Adjust Provenance confidence
            if positive >= POSITIVE_THRESHOLD:
                await self._boost_provenance(run_id, delta=0.1)
                await self._mark_sample(run_id, "positive")
            elif negative >= NEGATIVE_THRESHOLD:
                await self._mark_sample(run_id, "negative")

            # Clean up processed
            del self._run_signals[run_id]

        self._buffer.clear()
        _log.debug(f"ImplicitFeedback: flushed {len(self._buffer)} signals")

    async def _boost_provenance(self, run_id: str, delta: float = 0.1):
        """调高 Provenance 权重"""
        try:
            from core.harness.knowledge.provenance import get_provenance_tracker
            tracker = get_provenance_tracker()
            prov = tracker.get_provenance(run_id)
            if prov:
                for c in prov.citations:
                    c.confidence = min(1.0, c.confidence + delta)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    async def _mark_sample(self, run_id: str, label: str):
        """标记 execution_store 为正/负样本"""
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            await store.set_meta(run_id, "implicit_label", label)
            _log.info(f"ImplicitFeedback: marked {run_id} as {label}")
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    def _adjust_weights(self):
        """EMA-smoothed multi-objective weight adjustment based on recent signals.
        
        Signals → objectives mapping:
          copy_full     → accuracy (user found answer complete)
          re_query      → accuracy penalty (answer insufficient)
          repeat_query  → accuracy penalty (answer wrong)
          abandon       → conciseness (user gave up reading long output)
          
        Protected: all weights clamped to [0.1, 0.8], then normalized to sum=1.0.
        """
        recent = self._buffer[-self._adjust_interval:] if len(self._buffer) >= self._adjust_interval else self._buffer
        if not recent:
            return

        # Compute target adjustments from signals
        targets = {"accuracy": 0.0, "speed": 0.0, "conciseness": 0.0}
        adjust_count = 0
        for s in recent:
            if s.signal_type in ("copy_full", "select_text"):
                targets["accuracy"] += 0.02
                adjust_count += 1
            elif s.signal_type == "re_query":
                targets["accuracy"] -= 0.02
                adjust_count += 1
            elif s.signal_type == "repeat_query":
                targets["accuracy"] -= 0.03
                targets["conciseness"] += 0.01
                adjust_count += 1
            elif s.signal_type == "abandon":
                targets["conciseness"] += 0.02
                targets["accuracy"] -= 0.01
                adjust_count += 1

        if adjust_count == 0:
            return

        # EMA smoothing: new = old * (1 - alpha) + target * alpha
        alpha = self._ema_alpha
        for dim in targets:
            old = self._objective_weights[dim]
            target = targets[dim]
            # Target is a delta, so new = old + delta * alpha
            self._objective_weights[dim] = old + target * alpha

        # Clamp to [0.1, 0.8]
        for dim in self._objective_weights:
            self._objective_weights[dim] = max(0.1, min(0.8, self._objective_weights[dim]))

        # Normalize to sum=1.0
        total = sum(self._objective_weights.values())
        if total > 0:
            for dim in self._objective_weights:
                self._objective_weights[dim] /= total

    def get_priority_hint(self) -> str:
        """返回当前 Action 的优先级提示字符串 (用于注入 Agent system prompt)。"""
        w = self._objective_weights
        top = max(w, key=w.get)
        if top == "accuracy":
            return "优先保证回答的准确性和完整性，必要时可以多花时间查找资料。"
        elif top == "speed":
            return "优先快速响应用户，在保证基本准确的前提下尽量简洁。"
        else:
            return "优先输出简洁明确的答案，避免冗长的解释，直击要点。"

    def get_objective_weights(self) -> Dict[str, float]:
        """Get current objective weights (for diagnostics)."""
        return dict(self._objective_weights)

    def get_stats(self) -> Dict[str, Any]:
        """获取收集器统计"""
        return {
            "buffer_size": len(self._buffer),
            "tracked_runs": len(self._run_signals),
            "sample_count": self._sample_count,
            "objective_weights": dict(self._objective_weights),
            "priority_hint": self.get_priority_hint(),
            "signal_distribution": {
                "copy_full": sum(1 for s in self._buffer if s.signal_type == "copy_full"),
                "select_text": sum(1 for s in self._buffer if s.signal_type == "select_text"),
                "re_query": sum(1 for s in self._buffer if s.signal_type == "re_query"),
            },
        }


# ── Global singleton ─────────────────────────────────────────────────────────

_collector: Optional[ImplicitFeedbackCollector] = None

def get_implicit_feedback_collector() -> ImplicitFeedbackCollector:
    global _collector
    if _collector is None:
        _collector = ImplicitFeedbackCollector()
    return _collector
