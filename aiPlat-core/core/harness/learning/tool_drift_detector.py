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


# ── Realtime anomaly types (Layer 1: 感知) ──

class AnomalyType(Enum):
    REDUNDANT_CALL = "redundant_call"       # 同工具+同参数 短时间高频重复
    OUTLIER_LATENCY = "outlier_latency"     # 单次延迟远超 P95
    CASCADE_FAILURE = "cascade_failure"     # 连续 N 次全失败
    CIRCUIT_OPEN = "circuit_open"           # 熔断器触发


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


@dataclass
class RealtimeAlert:
    anomaly_type: AnomalyType
    tool_name: str
    detail: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class CircuitBreaker:
    tool_name: str
    opened_at: float
    cooldown_s: float
    reason: str
    reject_count: int = 0


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

        # ── Realtime mode: small window, high frequency checks ──
        self._realtime_buffer: Dict[str, Deque[ToolCallRecord]] = defaultdict(
            lambda: deque(maxlen=int(os.getenv("AIPLAT_REALTIME_WINDOW_SIZE", "20")))
        )
        self._realtime_enabled = os.getenv("AIPLAT_REALTIME_ANOMALY_ENABLED", "true") \
            .lower() in ("1", "true", "yes")
        self._redundant_interval = float(os.getenv("AIPLAT_REALTIME_REDUNDANT_INTERVAL", "3.0"))
        self._outlier_ratio = float(os.getenv("AIPLAT_REALTIME_OUTLIER_RATIO", "3.0"))
        self._cascade_threshold = int(os.getenv("AIPLAT_REALTIME_CASCADE_THRESHOLD", "5"))

        # ── Circuit breaker ──
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._circuit_cooldown = float(os.getenv("AIPLAT_CIRCUIT_COOLDOWN", "60"))

        # ── Alert cooldown (prevent alert fatigue) ──
        self._alert_cooldown: Dict[str, float] = {}
        self._alert_cooldown_s = float(os.getenv("AIPLAT_ALERT_COOLDOWN", "300"))

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
                pass  # noqa: normal-cancellation

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
        # Circuit breaker: reject calls when breaker is open
        if tool_name and tool_name in self._circuit_breakers:
            cb = self._circuit_breakers[tool_name]
            if time.time() - cb.opened_at < cb.cooldown_s:
                cb.reject_count += 1
                self._alert(AnomalyType.CIRCUIT_OPEN, tool_name,
                            f"Rejected (#{cb.reject_count}): {cb.reason}")
                return
            else:
                del self._circuit_breakers[tool_name]
                logger.info("Circuit breaker auto-closed for %s", tool_name)

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
        # Async queue (nightly batch drift detection — unchanged)
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            pass  # noqa: cleanup-best-effort

        # Sync realtime anomaly check
        if self._realtime_enabled and tool_name:
            self._check_realtime(tool_name, request_schema, status_code,
                                 latency_ms, error_code, record)

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
                logging.getLogger(__name__).debug('_replay_validate: mapping replay failed', exc_info=True)

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

    # ── Realtime anomaly checks ──

    def _check_realtime(self, tool_name: str, request_schema: dict,
                        status_code: int, latency_ms: float, error_code: str,
                        record: ToolCallRecord) -> None:
        """Synchronous realtime checks — ring buffer only, zero I/O."""
        now = time.time()
        args_hash = self._hash_args(request_schema)
        buf = self._realtime_buffer[tool_name]
        buf.append(record)

        # Check 1: REDUNDANT_CALL — same tool + same args in recent window
        redundant = 0
        for r in reversed(list(buf)[-10:]):
            if (now - r.timestamp) > self._redundant_interval:
                break
            if r.status_code == 200 and self._hash_args(r.request_schema) == args_hash:
                redundant += 1
        if redundant >= 3:
            self._alert(AnomalyType.REDUNDANT_CALL, tool_name,
                        f"{redundant} identical calls in {self._redundant_interval}s")

        # Check 2: OUTLIER_LATENCY — single call abnormally slow
        latencies = [r.latency_ms for r in buf if r.latency_ms > 0 and r.status_code == 200]
        if len(latencies) >= 5:
            p95 = sorted(latencies)[int(len(latencies) * 0.95)]
            if latency_ms > p95 * self._outlier_ratio and latency_ms > 100:
                self._alert(AnomalyType.OUTLIER_LATENCY, tool_name,
                            f"{latency_ms:.0f}ms > P95={p95:.0f}ms × {self._outlier_ratio}")

        # Check 3: CASCADE_FAILURE — consecutive failures
        recent = list(buf)[-self._cascade_threshold:]
        if len(recent) >= self._cascade_threshold:
            if all(r.status_code != 200 for r in recent):
                self._unstable_tools.add(tool_name)
                self._circuit_breakers[tool_name] = CircuitBreaker(
                    tool_name=tool_name, opened_at=now,
                    cooldown_s=self._circuit_cooldown,
                    reason=f"Last {len(recent)} calls all failed",
                )
                self._alert(AnomalyType.CASCADE_FAILURE, tool_name,
                            f"Opened circuit (cooldown={self._circuit_cooldown}s)")

    @staticmethod
    def _hash_args(request_schema) -> str:
        return hashlib.md5(str(request_schema).encode()).hexdigest()[:12]

    def _alert(self, anomaly_type: AnomalyType, tool_name: str, detail: str) -> None:
        """Cooldown-controlled alert to EventBus + reaction triggers."""
        cooldown_key = f"{tool_name}:{anomaly_type.value}"
        now = time.time()
        last = self._alert_cooldown.get(cooldown_key, 0)
        if now - last < self._alert_cooldown_s:
            return
        self._alert_cooldown[cooldown_key] = now

        logger.warning("REALTIME ⚡ %s: %s %s", anomaly_type.value, tool_name, detail)
        try:
            from core.harness.observation.event_bus import EventBus
            EventBus.publish("system", {
                "type": "tool_anomaly",
                "anomaly": anomaly_type.value,
                "tool": tool_name,
                "detail": detail,
                "timestamp": now,
            })
        except Exception:
            logging.getLogger(__name__).debug('_record_anomaly failed', exc_info=True)

        # Layer 2+3 glue: realtime reaction via running event loop
        try:
            loop = asyncio.get_running_loop()
            if anomaly_type in (AnomalyType.REDUNDANT_CALL, AnomalyType.OUTLIER_LATENCY):
                loop.create_task(self._trigger_pattern_analysis(tool_name, anomaly_type, detail))
            elif anomaly_type == AnomalyType.CASCADE_FAILURE:
                loop.create_task(self._trigger_circuit_breaker_skill(tool_name, detail))
        except RuntimeError:
            pass  # noqa: cleanup-best-effort

    async def _trigger_pattern_analysis(self, tool_name: str,
                                        anomaly_type: AnomalyType, detail: str) -> None:
        try:
            from core.harness.memory.pattern_accumulator import get_pattern_accumulator
            acc = get_pattern_accumulator()
            await acc.ingest_anomaly(tool_name, {
                "type": anomaly_type.value,
                "detail": detail,
                "timestamp": time.time(),
            })
        except Exception:
            logger.debug("Pattern analysis trigger failed", exc_info=True)

    async def _trigger_circuit_breaker_skill(self, tool_name: str, detail: str) -> None:
        try:
            from core.harness.learning.skill_evolver import get_skill_evolver, SharedSkillDraft
            evolver = get_skill_evolver()
            draft = SharedSkillDraft(
                pattern_hash=hashlib.md5(f"cb:{tool_name}".encode()).hexdigest()[:16],
                tool_sequence=[tool_name, "circuit_breaker"],
                tenant_count=1,
                total_frequency=1,
                suggestion=f"级联失败触发: {detail}. 建议为 {tool_name} 配置降级策略。",
                source="realtime_anomaly",
            )
            await evolver.submit_shared_draft(draft)
        except Exception:
            logger.debug("Circuit breaker skill trigger failed", exc_info=True)

    def _call_llm_for_schema(self, tool_name: str, samples: List[Dict]) -> Dict[str, str]:
        """Generate new field extraction mapping from samples using LLM.

        Returns parsed JSON mapping dict, or empty dict on failure.
        NOTE: This is synchronous; caller must handle async context.
        For EvolutionEngine nightly (always in async context), this
        resolves via the running event loop and returns real results.
        """
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
                # Run in existing event loop (EvolutionEngine nightly path)
                future = _asyncio.ensure_future(sys_llm_generate(
                    None, [{"role": "user", "content": prompt}],
                    model_name=best_model_for_purpose("chat"),
                    max_tokens=300,
                    temperature=0.1,
                ))
                try:
                    # Wait for result with timeout (non-blocking in async context)
                    result = loop.run_until_complete(
                        _asyncio.wait_for(future, timeout=5.0)
                    )
                    raw = getattr(result, "content", "") or str(result)
                    import re as _re
                    m = _re.search(r'\{[^{}]*\}', raw)
                    if m:
                        return json.loads(m.group())
                except Exception:
                    logger.debug("LLM schema call timed out or failed for %s", tool_name, exc_info=True)
            return {}
        except Exception:
            logger.debug("LLM schema generation unavailable for %s", tool_name, exc_info=True)
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

    def _inject_realtime(self, tool_name: str, request_schema: dict,
                         status_code: int = 200, latency_ms: float = 100,
                         error_code: Optional[str] = None) -> None:
        """Direct realtime buffer injection for tests (triggers _check_realtime)."""
        record = ToolCallRecord(
            tool_name=tool_name,
            timestamp=time.time(),
            request_schema=request_schema,
            response_data={},
            status_code=status_code,
            latency_ms=latency_ms,
            error_code=error_code,
        )
        self._realtime_buffer[tool_name].append(record)
        # Trigger realtime check so anomaly detection runs
        if self._realtime_enabled:
            self._check_realtime(tool_name, request_schema, status_code,
                                 latency_ms, error_code, record)

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

    def get_realtime_stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._realtime_enabled,
            "tools_monitored": len(self._realtime_buffer),
            "circuit_breakers_open": {
                t: {"opened_at": cb.opened_at, "cooldown_s": cb.cooldown_s,
                    "reject_count": cb.reject_count, "reason": cb.reason}
                for t, cb in self._circuit_breakers.items()
            },
            "buffer_sizes": {t: len(buf) for t, buf in self._realtime_buffer.items()},
            "unstable_tools": list(self._unstable_tools),
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

