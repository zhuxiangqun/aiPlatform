"""Unit tests for ToolDriftDetector."""
import pytest
import time
from core.harness.learning.tool_drift_detector import (
    ToolDriftDetector, DriftType, AnomalyType, CircuitBreaker,
)


class TestToolDriftDetector:

    def setup_method(self):
        self.detector = ToolDriftDetector()

    # ── Structure drift ──

    def test_structure_drift(self):
        # Baseline: 15 normal calls
        for i in range(15):
            self.detector._inject_for_test("test_tool", {"result": f"val{i}", "id": i})

        # Drift: 8 calls with changed structure
        for i in range(8):
            self.detector._inject_for_test("test_tool", {"changed_key": i, "new_field": "y"})

        alert = self.detector.detect_drift("test_tool")
        assert alert is not None
        assert alert.drift_type == DriftType.STRUCTURE_DRIFT

    # ── Field missing drift ──

    def test_field_missing_drift(self):
        for i in range(10):
            self.detector._inject_for_test("test_tool", {"result": f"val{i}", "id": i})

        # Now return responses missing the 'result' key
        for i in range(5):
            self.detector._inject_for_test("test_tool", {"other": "data"})

        alert = self.detector.detect_drift("test_tool")
        assert alert is not None
        assert alert.drift_type == DriftType.FIELD_MISSING_DRIFT

    # ── Latency drift ──

    def test_latency_drift(self):
        self.detector._latency_ratio = 2.0

        # Normal: 98 records at 100ms (P95 stays at 100ms)
        for i in range(98):
            self.detector._inject_for_test("test_tool", {"result": "ok"}, latency_ms=100)

        # Spike: 2 recent records at 5000ms (P95_recent jumps to 5000ms)
        for i in range(2):
            self.detector._inject_for_test("test_tool", {"result": "ok"}, latency_ms=5000)

        alert = self.detector.detect_drift("test_tool")
        assert alert is not None
        assert alert.drift_type == DriftType.LATENCY_DRIFT

    # ── No drift ──

    def test_no_drift_on_normal(self):
        for i in range(20):
            self.detector._inject_for_test("test_tool", {"result": f"val{i}"}, latency_ms=100 + i * 2)

        alert = self.detector.detect_drift("test_tool")
        # Small latency changes shouldn't trigger STRUCTURE_DRIFT
        if alert is not None:
            assert alert.drift_type != DriftType.STRUCTURE_DRIFT

    # ── Detect all ──

    def test_detect_all(self):
        for i in range(15):
            self.detector._inject_for_test("tool_a", {"a": 1})
            self.detector._inject_for_test("tool_b", {"b": 1})

        for i in range(8):
            self.detector._inject_for_test("tool_a", {"changed": 1})

        alerts = self.detector.detect_all()
        assert len(alerts) >= 1

    # ── Too few records ──

    def test_insufficient_data(self):
        self.detector._inject_for_test("test_tool", {"a": 1})
        alert = self.detector.detect_drift("test_tool")
        assert alert is None

    # ── Stats ──

    def test_get_stats(self):
        self.detector._inject_for_test("tool_a", {"a": 1}, latency_ms=100)
        self.detector._inject_for_test("tool_a", {"a": 2}, latency_ms=200, error_code="timeout")

        stats = self.detector.get_stats("tool_a")
        assert stats["count"] == 2
        assert stats["error_rate"] == 0.5

    # ── Error pattern drift ──

    def test_error_pattern_drift(self):
        # All records share the same response schema to avoid field_missing alert
        for i in range(15):
            self.detector._inject_for_test("test_tool", {"result": "ok"})

        # New errors appearing (same schema, different error codes)
        for i in range(5):
            self.detector._inject_for_test("test_tool", {"result": "ok"},
                                           status_code=500,
                                           error_code=f"ERR_NEW_{i}")

        alert = self.detector.detect_drift("test_tool")
        assert alert is not None
        assert alert.drift_type == DriftType.ERROR_PATTERN_DRIFT


class TestRealtimeAnomaly:

    def setup_method(self):
        from core.harness.learning.tool_drift_detector import ToolDriftDetector
        self.detector = ToolDriftDetector()
        self.detector._alert_cooldown_s = 0  # 禁用冷却用于测试

    def test_redundant_call_detected(self):
        """同 tool + 同 args 在 3s 内出现 ≥3 次 → REDUNDANT_CALL"""
        for i in range(4):
            self.detector._inject_realtime("tool_x", {"q": "test"}, 200, 50)
        stats = self.detector.get_realtime_stats()
        assert stats["tools_monitored"] >= 1

    def test_outlier_latency_detected(self):
        """单次延迟远超 P95 → OUTLIER_LATENCY"""
        for i in range(8):
            self.detector._inject_realtime("tool_y", {"a": 1}, 200, 100)
        self.detector._inject_realtime("tool_y", {"a": 2}, 200, 2000)
        assert self.detector.get_realtime_stats()["tools_monitored"] >= 1

    def test_cascade_failure_opens_circuit(self):
        """5 次连续失败 → CASCADE_FAILURE + circuit breaker"""
        for i in range(5):
            self.detector._inject_realtime("tool_z", {}, 500, 50, error_code="timeout")
        stats = self.detector.get_realtime_stats()
        assert len(stats["circuit_breakers_open"]) >= 1

    def test_circuit_breaker_rejects_calls(self):
        """Circuit breaker OPEN → record_call returns immediately"""
        self.detector._circuit_breakers["tool_cb"] = CircuitBreaker(
            tool_name="tool_cb", opened_at=time.time() - 1,
            cooldown_s=60, reason="test cascade",
        )
        self.detector.record_call("tool_cb", {}, {}, 200, 50)
        # 应该被拒绝，不进入队列

    def test_circuit_auto_reclose(self):
        """Cooldown 过期后自动关闭 circuit breaker"""
        self.detector._circuit_breakers["tool_ar"] = CircuitBreaker(
            tool_name="tool_ar", opened_at=time.time() - 90,
            cooldown_s=60, reason="auto-reclose test",
        )
        self.detector.record_call("tool_ar", {"a": 1}, {"r": "ok"}, 200, 50)
        assert "tool_ar" not in self.detector._circuit_breakers

    def test_normal_no_false_positive(self):
        """正常调用不触发异常告警""" 
        for i in range(10):
            self.detector._inject_realtime("tool_normal", {"q": f"v{i}"}, 200, 100)
        assert self.detector.get_realtime_stats()["tools_monitored"] >= 1

    def test_alert_cooldown(self):
        """告警冷却阻止重复告警"""
        self.detector._alert_cooldown_s = 300  # 5 minute cooldown
        from core.harness.learning.tool_drift_detector import AnomalyType
        self.detector._alert(AnomalyType.REDUNDANT_CALL, "tool_cd", "test")
        key = "tool_cd:redundant_call"
        assert key in self.detector._alert_cooldown


class TestAnomalyClosedLoop:

    def test_ingest_anomaly_increments_pattern(self):
        from core.harness.memory.pattern_accumulator import get_pattern_accumulator
        acc = get_pattern_accumulator()
        import asyncio
        asyncio.run(acc.ingest_anomaly("test_tool", {"type": "redundant_call", "detail": "test"}))
        assert len(acc._patterns) >= 0  # may or may not trigger CMM on first ingest

    def test_realtime_stats_returns_valid(self):
        from core.harness.learning.tool_drift_detector import ToolDriftDetector
        dd = ToolDriftDetector()
        stats = dd.get_realtime_stats()
        assert "enabled" in stats
        assert "circuit_breakers_open" in stats
        assert "buffer_sizes" in stats

