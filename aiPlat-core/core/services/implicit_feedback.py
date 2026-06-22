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

import asyncio, os, time, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.implicit_feedback")


@dataclass
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


class ImplicitFeedbackCollector:
    """隐式反馈收集器 — 批量聚合 + 自动调权"""

    def __init__(self):
        self._buffer: List[ImplicitSignal] = []
        self._run_signals: Dict[str, List[ImplicitSignal]] = {}  # run_id → signals
        self._enabled = os.getenv("AIPLAT_IMPLICIT_FEEDBACK_ENABLED", "true").lower() not in ("0", "false", "no")

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

        # Flush when buffer is full
        if len(self._buffer) >= FLUSH_SIZE:
            await self._flush()

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
        except Exception:
            pass

    async def _mark_sample(self, run_id: str, label: str):
        """标记 execution_store 为正/负样本"""
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            await store.set_meta(run_id, "implicit_label", label)
            _log.info(f"ImplicitFeedback: marked {run_id} as {label}")
        except Exception:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """获取收集器统计"""
        return {
            "buffer_size": len(self._buffer),
            "tracked_runs": len(self._run_signals),
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
