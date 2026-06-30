"""Unit tests for ToolDriftDetector."""
import pytest
from core.harness.learning.tool_drift_detector import (
    ToolDriftDetector, DriftType,
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
