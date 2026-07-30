"""
PatternAccumulator — CMM 观察层 + MetaClaw 双轨综合。

从 ExecutionStore 提取推理模式（工具序列指纹），跨会话累积重复模式，
在频次达标时触发 AutoLearner Draft 生成。同时支持成功/失败双轨比较。

CMM (Cognitive Memory Manager):
  - 准则 1: 跨会话频次 ≥ 3
  - 准则 2: 检索验证（已有 Skill 覆盖则跳过）
  - 准则 3: 人工审批（复用现有 ApprovalGate）

MetaClaw: 同一任务的成功 vs 失败轨迹比较
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

_log = logging.getLogger(__name__)


@dataclass
class Pattern:
    """跨会话累积的推理模式。"""
    hash: str
    tool_sequence: Tuple[str, ...]
    frequency: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sessions: Set[str] = field(default_factory=set)
    tenants: Set[str] = field(default_factory=set)

    def meets_frequency(self, threshold: int = 3) -> bool:
        return self.frequency >= threshold

    def meets_tenant_threshold(self, threshold: int = 2) -> bool:
        return len(self.tenants) >= threshold


@dataclass
class ComparisonReport:
    """MetaClaw 双轨比较报告。"""
    intent: str
    success_path: List[str]
    failure_path: List[str]
    suggestion: str


class PatternAccumulator:
    """CMM 观察层 — 提取推理DAG，跨会话累积，双轨比较。

    从 ExecutionStore.syscall_events 提取工具序列作为模式指纹（v1 工具序列 hash）。
    v2 可升级为 intent→action→observation 三元组。
    """

    def __init__(self, frequency_threshold: int = 3):
        self._freq_threshold = frequency_threshold
        self._patterns: Dict[str, Pattern] = {}

    async def _ensure_store(self):
        from core.services.execution_store import get_execution_store
        return get_execution_store()

    # ── CMM: 提取推理 DAG ────────────────────────────

    def _extract_tool_sequence(self, events: List[Dict]) -> Tuple[str, ...]:
        """从 syscall_events 提取工具调用序列。"""
        return tuple(
            str(e.get("name") or e.get("tool_name") or e.get("kind", ""))
            for e in events
            if (e.get("kind") == "tool" or e.get("event_type") == "tool_call")
            and not str(e.get("name", "")).startswith("sys_")
        )

    def _get_or_create(self, pattern_hash: str, tool_seq: Tuple[str, ...]) -> Pattern:
        if pattern_hash not in self._patterns:
            self._patterns[pattern_hash] = Pattern(
                hash=pattern_hash,
                tool_sequence=tool_seq,
                first_seen=datetime.now(timezone.utc).isoformat(),
            )
        return self._patterns[pattern_hash]

    async def extract_from_run(self, run_id: str, tenant_id: str = "") -> Optional[Pattern]:
        """从单次执行的 syscall_events 提取工具序列作为模式指纹。"""
        store = await self._ensure_store()
        events = await store.get_syscall_events(run_id) if hasattr(store, 'get_syscall_events') else []
        if not events:
            return None

        tool_seq = self._extract_tool_sequence(events)
        if len(tool_seq) < 1:
            return None

        pattern_hash = hashlib.md5(str(tool_seq).encode()).hexdigest()
        pattern = self._get_or_create(pattern_hash, tool_seq)
        pattern.frequency += 1
        pattern.last_seen = datetime.now(timezone.utc).isoformat()
        pattern.sessions.add(run_id)
        if tenant_id:
            pattern.tenants.add(tenant_id)
        return pattern if pattern.meets_frequency(self._freq_threshold) else None

    async def extract_from_failure(
        self, run_id: str, error_context: Dict[str, Any] = None,
        tenant_id: str = "",
    ) -> Optional[Pattern]:
        """CMM 准则 1+2: 频次 ≥3 + 检索验证通过才生成 Draft。"""
        pattern = await self.extract_from_run(run_id, tenant_id=tenant_id)
        if not pattern:
            return None

        # 准则 2: 检索验证 — 已有 Skill 覆盖此模式？
        try:
            from core.harness.integration import get_skill_registry
            reg = get_skill_registry()
            similar = reg.search_by_pattern(list(pattern.tool_sequence)) if hasattr(reg, 'search_by_pattern') else None
            if similar:
                _log.info(f"PatternAccumulator: pattern {pattern.hash[:8]} already covered by skill {similar}")
                return None
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        _log.info(f"PatternAccumulator: pattern {pattern.hash[:8]} freq={pattern.frequency} → triggering draft")
        
        # Phase 6: CMM graduation — promote high-frequency patterns to AutoLearner pipeline
        try:
            from core.harness.learning.cmm_graduation import get_cmm_graduation
            cmm = get_cmm_graduation()
            import asyncio
            asyncio.create_task(cmm.graduate(pattern.hash, error_context))
        except Exception:
            logging.getLogger(__name__).debug('extract_from_failure failed', exc_info=True)
        
        return pattern

    async def ingest_anomaly(self, tool_name: str, anomaly: Dict[str, Any]) -> None:
        """实时接入：将异常事件转化为 Pattern（CMM 观察层 Layer 2）。

        与 extract_from_failure 不同：extract_from_failure 读完整 syscall_events，
        ingest_anomaly 只接收单个异常事件，用于实时模式。
        """
        anomaly_type = anomaly.get("type", "unknown")
        tool_seq = (tool_name, f"anomaly:{anomaly_type}")
        pattern_hash = hashlib.md5(str(tool_seq).encode()).hexdigest()
        pattern = self._get_or_create(pattern_hash, tool_seq)
        pattern.frequency += 1
        pattern.last_seen = datetime.now(timezone.utc).isoformat()
        if pattern.meets_frequency(self._freq_threshold):
            _log.info("Anomaly pattern %s freq=%d → triggering CMM", pattern_hash[:8], pattern.frequency)
            try:
                from core.harness.learning.cmm_graduation import get_cmm_graduation
                cmm = get_cmm_graduation()
                cmm.graduate(pattern_hash, {"anomaly": anomaly})
            except Exception:
                logging.getLogger(__name__).debug('ingest_anomaly failed', exc_info=True)

    # ── MetaClaw: 双轨综合 ────────────────────────────

    async def compare_success_failure(
        self, intent: str, days: int = 30,
    ) -> Optional[ComparisonReport]:
        """MetaClaw 双轨综合：比较同一任务的成功和失败轨迹。

        不只看失败错了什么，也看成功做对了什么。
        两者工具序列不同 → 提取差异 → 生成建议。
        """
        store = await self._ensure_store()
        success_runs = await store.get_runs(intent=intent, status="completed", days=days) \
            if hasattr(store, 'get_runs') else []
        failure_runs = await store.get_runs(intent=intent, status="failed", days=days) \
            if hasattr(store, 'get_runs') else []

        if len(success_runs) < 1 or len(failure_runs) < 1:
            return None

        success_events = await store.get_syscall_events(success_runs[0].id) \
            if hasattr(store, 'get_syscall_events') else []
        failure_events = await store.get_syscall_events(failure_runs[0].id) \
            if hasattr(store, 'get_syscall_events') else []

        success_seq = self._extract_tool_sequence(success_events)
        failure_seq = self._extract_tool_sequence(failure_events)

        if set(success_seq) == set(failure_seq):
            return None  # 工具序列相同 → 差异不在此

        return ComparisonReport(
            intent=intent,
            success_path=list(success_seq),
            failure_path=list(failure_seq),
            suggestion=(
                f"Task '{intent}': "
                f"success used {list(set(success_seq) - set(failure_seq))}, "
                f"failure used {list(set(failure_seq) - set(success_seq))}. "
                f"Recommend adopting success path as Skill."
            ),
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "total_patterns": len(self._patterns),
            "frequent_patterns": sum(1 for p in self._patterns.values() if p.meets_frequency()),
            "multi_tenant_patterns": sum(1 for p in self._patterns.values() if p.meets_tenant_threshold()),
        }


_accumulator: Optional[PatternAccumulator] = None


def get_pattern_accumulator() -> PatternAccumulator:
    global _accumulator
    if _accumulator is None:
        _accumulator = PatternAccumulator()
    return _accumulator
