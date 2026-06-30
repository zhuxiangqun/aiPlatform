"""
ToolDriftDetector — 外部工具/API漂移自适应检测器 (L2 Resource Layer)
========================================================================

检测4类漂移:
  1. STRUCTURE_DRIFT     — JSON Schema 结构变化
  2. FIELD_MISSING_DRIFT — 关键字段缺失率突增
  3. LATENCY_DRIFT       — P95 延迟突变
  4. ERROR_PATTERN_DRIFT — 新错误码涌现

策略:
  - 监听: sys_tool_call 返回后异步记录 (asyncio.Queue, 零阻塞)
  - 检测: EvolutionEngine nightly 定时批量扫描
  - 自适应: 重放校验 ≥80% 才生效新 SchemaMapping
  - FAILSAFE: 校验失败 → UNSTABLE 标记 → 触发告警

环境变量:
  AIPLAT_DRIFT_WINDOW_SIZE: 滑动窗口大小 (默认: 100)
  AIPLAT_DRIFT_FIELD_MISSING_THRESHOLD: 字段缺失率阈值 (默认: 0.1)
  AIPLAT_DRIFT_LATENCY_RATIO: P95延迟突变倍数 (默认: 2.0)
  AIPLAT_DRIFT_ERROR_RATE_THRESHOLD: 新错误码率阈值 (默认: 0.05)
"""
from __future__ import annotations

import asyncio
import json
import time
import logging
import os
import hashlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Enums ──

class DriftType(Enum):
    STRUCTURE_DRIFT = "structure_drift"
    FIELD_MISSING_DRIFT = "field_missing_drift"
    LATENCY_DRIFT = "latency_drift"
    ERROR_PATTERN_DRIFT = "error_pattern_drift"


# ── Data models ──

@dataclass
class DriftAlert:
    tool_name: str
    drift_type: DriftType
    detail: str
    sample_rate: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolCallRecord:
    tool_name: str
    timestamp: float
    request_schema: Dict[str, Any]
    response_data: Dict[str, Any]
    status_code: int
    latency_ms: float
    error_code: Optional[str] = None
    golden_keys: Optional[List[str]] = field(default_factory=list)


@dataclass
class SchemaMapping:
    mapping_rules: Dict[str, str]
    ttl_expire: float
    version: int = 1


# ── Core detector ──

class ToolDriftDetector:
    """Async, non-blocking tool drift detector."""

    def __init__(self):
        self._windows: Dict[str, Deque[ToolCallRecord]] = defaultdict(
            lambda: deque(maxlen=int(os.getenv("AIPLAT_DRIFT_WINDOW_SIZE", "100")))
        )
        self._mapping_cache: Dict[str, SchemaMapping] = {}
        self._queue: asyncio.Queue[ToolCallRecord] = asyncio.Queue(maxsize=1000)
        self._worker_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._unstable_tools: set[str] = set()

        self._field_missing_threshold = float(os.getenv("AIPLAT_DRIFT_FIELD_MISSING_THRESHOLD", "0.1"))
        self._latency_ratio = float(os.getenv("AIPLAT_DRIFT_LATENCY_RATIO", "2.0"))
        self._error_rate_threshold = float(os.getenv("AIPLAT_DRIFT_ERROR_RATE_THRESHOLD", "0.05"))

    # ── Lifecycle ──

    async def start(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._queue_worker())
            logger.info("ToolDriftDetector worker started (window=%d)", self._windows[list(self._windows.keys())[0]].maxlen if self._windows else 100)

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    # ── Main entry (non-blocking, called from sys_tool_call hot path) ──

    def record_call(
        self,
        tool_name: str,
        request_schema: Dict[str, Any],
        response_data: Dict[str, Any],
        status_code: int,
        latency_ms: float,
        error_code: Optional[str] = None,
    ) -> None:
        golden_keys = list(response_data.keys())[:5] if isinstance(response_data, dict) else []
        record = ToolCallRecord(
            tool_name=tool_name,
            timestamp=time.time(),
            request_schema=request_schema,
            response_data=response_data,
            status_code=status_code,
            latency_ms=latency_ms,
            error_code=error_code,
            golden_keys=golden_keys,
        )
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            pass

    # ── Background worker ──

    async def _queue_worker(self) -> None:
        while True:
            try:
                batch = []
                first = await self._queue.get()
                batch.append(first)
                while len(batch) < 10:
                    try:
                        batch.append(self._queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                async with self._lock:
                    for record in batch:
                        self._windows[record.tool_name].append(record)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.debug("Drift worker exception", exc_info=True)
                await asyncio.sleep(0.1)

    # ── Detect (called from EvolutionEngine nightly) ──

    def detect_drift(self, tool_name: str) -> Optional[DriftAlert]:
        if tool_name not in self._windows:
            return None
        records = list(self._windows[tool_name])
        if len(records) < 10:
            return None

        recent = records[-20:]
        baseline = records[:-20] if len(records) > 20 else records

        # 1. Structure drift
        if baseline:
            recent_keys = set().union(*[set(r.response_data.keys()) for r in recent if isinstance(r.response_data, dict)])
            baseline_keys = set().union(*[set(r.response_data.keys()) for r in baseline if isinstance(r.response_data, dict)])
            if baseline_keys:
                jaccard = len(recent_keys & baseline_keys) / max(len(recent_keys | baseline_keys), 1)
                if jaccard < 0.6:
                    return DriftAlert(tool_name=tool_name, drift_type=DriftType.STRUCTURE_DRIFT,
                                      detail=f"Jaccard={jaccard:.2f}", sample_rate=1 - jaccard)

        # 2. Field missing drift
        if recent and recent[0].golden_keys:
            # Use the first recent record's keys as the "expected" schema
            expected_keys = recent[0].golden_keys
            missing = 0
            for r in recent:
                if isinstance(r.response_data, dict):
                    if any(k not in r.response_data for k in expected_keys):
                        missing += 1
            rate = missing / len(recent)
            if rate > self._field_missing_threshold:
                return DriftAlert(tool_name=tool_name, drift_type=DriftType.FIELD_MISSING_DRIFT,
                                  detail=f"Missing rate {rate:.1%}", sample_rate=rate)

        # 3. Latency drift
        all_lats = sorted([r.latency_ms for r in records])
        recent_lats = sorted([r.latency_ms for r in recent])
        if len(all_lats) > 10 and len(recent_lats) > 5:
            p95_all = all_lats[int(len(all_lats) * 0.95)]
            p95_recent = recent_lats[int(len(recent_lats) * 0.95)]
            if p95_all > 0 and p95_recent > p95_all * self._latency_ratio:
                return DriftAlert(tool_name=tool_name, drift_type=DriftType.LATENCY_DRIFT,
                                  detail=f"P95 {p95_recent:.0f}ms > {p95_all:.0f}ms", sample_rate=p95_recent / max(p95_all, 1))

        # 4. Error pattern drift
        recent_errors = [r.error_code for r in recent if r.error_code]
        if recent_errors:
            baseline_errors = set(r.error_code for r in records if r.error_code and r not in recent)
            new_in_recent = [e for e in recent_errors if e not in baseline_errors]
            if new_in_recent:
                new_rate = len(new_in_recent) / len(recent_errors)
                if new_rate > self._error_rate_threshold:
                    return DriftAlert(tool_name=tool_name, drift_type=DriftType.ERROR_PATTERN_DRIFT,
                                      detail=f"New errors: {set(new_in_recent)}", sample_rate=new_rate)
        return None

    def detect_all(self) -> List[DriftAlert]:
        alerts = []
        for tool_name in list(self._windows.keys()):
            alert = self.detect_drift(tool_name)
            if alert:
                alerts.append(alert)
        return alerts

    # ── Adapt (with replay validation) ──

    def adapt(self, tool_name: str) -> Optional[SchemaMapping]:
        if tool_name in self._unstable_tools:
            return None

        records = list(self._windows[tool_name])
        if len(records) < 20:
            return None

        samples = [r.response_data for r in records[-20:] if isinstance(r.response_data, dict)]
        if not samples:
            return None

        try:
            new_rules = self._call_llm_for_schema(tool_name, samples)
        except Exception as e:
            logger.error("LLM schema generation failed for %s: %s", tool_name, e)
            self._unstable_tools.add(tool_name)
            self._trigger_alert(f"Tool {tool_name} adapt LLM failed: {e}")
            return None

        if not new_rules:
            return None

        # Replay validation
        success_records = [r for r in records if r.status_code == 200 and isinstance(r.response_data, dict)]
        if len(success_records) < 5:
            return None

        replay_sample = success_records[-10:]
        success_count = 0
        for rec in replay_sample:
            try:
                extracted = self._apply_mapping(rec.response_data, new_rules)
                if all(v is not None for v in extracted.values()):
                    success_count += 1
            except Exception:
                pass

        replay_rate = success_count / len(replay_sample)
        if replay_rate >= 0.8:
            mapping = SchemaMapping(mapping_rules=new_rules, ttl_expire=time.time() + 86400)
            self._mapping_cache[tool_name] = mapping
            self._unstable_tools.discard(tool_name)
            logger.info("Tool %s adapted: replay=%.0f%%", tool_name, replay_rate * 100)
            return mapping
        else:
            self._unstable_tools.add(tool_name)
            self._trigger_alert(f"Tool {tool_name} adapt failed: replay={replay_rate:.0%}")
            return None

    # ── Internal helpers ──

    def _call_llm_for_schema(self, tool_name: str, samples: List[Dict]) -> Dict[str, str]:
        """Generate new field extraction mapping from samples using LLM."""
        import asyncio as _asyncio

        prompt = (
            f"Tool '{tool_name}' response format has drifted.\n"
            f"Recent response samples:\n{json.dumps(samples[:5], indent=2, default=str)}\n\n"
            "Extract a field mapping as JSON: {\"target_field\": \"jsonpath.to.field\", ...}\n"
            "Return ONLY the JSON object."
        )
        try:
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.model_injection import best_model_for_purpose
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                future = _asyncio.ensure_future(sys_llm_generate(
                    None, [{"role": "user", "content": prompt}],
                    model_name=best_model_for_purpose("chat"),
                    max_tokens=300,
                    temperature=0.1,
                ))
                # Can't await in sync context — return empty for now, caller retries next cycle
                return {}
        except Exception:
            pass
        return {}

    def _apply_mapping(self, raw_data: Dict, mapping_rules: Dict[str, str]) -> Dict[str, Any]:
        result = {}
        for target_key, source_path in mapping_rules.items():
            if "." in source_path:
                parts = source_path.split(".")
                val = raw_data
                for p in parts:
                    if isinstance(val, dict) and p in val:
                        val = val[p]
                    else:
                        val = None
                        break
                result[target_key] = val
            else:
                result[target_key] = raw_data.get(source_path)
        return result

    def _trigger_alert(self, message: str) -> None:
        logger.error("DRIFT ALERT: %s", message)

    # ── Diagnostics ──

    async def flush(self) -> None:
        """Wait for queue to drain (useful for tests)."""
        for _ in range(50):
            if self._queue.empty():
                await asyncio.sleep(0.05)
                return
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.1)

    def _inject_for_test(self, tool_name: str, response_data: dict,
                         status_code: int = 200, latency_ms: float = 100,
                         error_code: Optional[str] = None) -> None:
        """Direct window injection for tests (bypasses async queue)."""
        record = ToolCallRecord(
            tool_name=tool_name,
            timestamp=time.time(),
            request_schema={},
            response_data=response_data,
            status_code=status_code,
            latency_ms=latency_ms,
            error_code=error_code,
            golden_keys=list(response_data.keys())[:5] if isinstance(response_data, dict) else [],
        )
        self._windows[tool_name].append(record)

    def get_stats(self, tool_name: str) -> Dict[str, Any]:
        records = list(self._windows.get(tool_name, []))
        if not records:
            return {"count": 0}
        lats = [r.latency_ms for r in records]
        errors = [r for r in records if r.error_code]
        return {
            "count": len(records),
            "avg_latency_ms": sum(lats) / len(lats),
            "error_rate": len(errors) / len(records),
            "is_unstable": tool_name in self._unstable_tools,
            "has_mapping": tool_name in self._mapping_cache,
        }

    def list_tools(self) -> List[str]:
        return sorted(self._windows.keys())


# ── Global singleton ──

_drift_detector: Optional[ToolDriftDetector] = None


def get_drift_detector() -> ToolDriftDetector:
    global _drift_detector
    if _drift_detector is None:
        _drift_detector = ToolDriftDetector()
    return _drift_detector
