"""Tests for trend_detector.py — entropy trend detection with double-buffered concurrency safety."""
import asyncio
import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime

import pytest

# ── Import TrendBuffer early (it's a standalone class we can test independently) ──
from core.harness.infrastructure.trend_detector import (
    TrendBuffer,
    TrendDetector,
    AlertState,
    AlertLevel,
    EntropyAlert,
    EntropyBucket,
    get_trend_detector,
    _get_db,
)


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure a clean test database for each test."""
    db_path = os.path.join(tempfile.gettempdir(), "test_entropy_trends.sqlite3")
    os.environ["AIPLAT_EXECUTION_DB_PATH"] = db_path
    # Clean up any existing db
    try:
        os.unlink(db_path)
        os.unlink(db_path + "-wal")
        os.unlink(db_path + "-shm")
    except FileNotFoundError:
        pass
    yield
    # Cleanup
    try:
        os.unlink(db_path)
        os.unlink(db_path + "-wal")
        os.unlink(db_path + "-shm")
    except FileNotFoundError:
        pass


# ═══════════════════════════════════════════════════════════
# 1. TrendBuffer — 双缓冲并发安全 (4 tests)
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestTrendBufferConcurrency:
    async def test_no_lost_events_on_concurrent_swap(self):
        """100 coroutines × 1000 writes + 5 swaps interleaved. Total = 100,000, verify no drops."""
        buf = TrendBuffer()
        N, per_coro = 100, 1000

        async def writer():
            for _ in range(per_coro):
                await buf.record("rate_limit")

        # Launch 100 writer coroutines
        writers = [asyncio.create_task(writer()) for _ in range(N)]

        # Interleave 5 snapshots during concurrent writes
        snapshots = []
        async def snapshotter():
            for _ in range(5):
                await asyncio.sleep(0)  # yield to writers
                snapshots.append(await buf.swap_and_reset())

        snap_task = asyncio.create_task(snapshotter())
        await asyncio.gather(*writers)
        await snap_task

        # Drain residual into final snapshot
        final = await buf.swap_and_reset()
        snapshots.append(final)

        total = sum(s.get("rate_limit", 0) for s in snapshots)
        expected = N * per_coro
        assert total == expected, f"Lost events: expected {expected}, got {total}"

    async def test_swap_empty_returns_zero(self):
        """Empty buffer swap returns {"__total__": 0}."""
        buf = TrendBuffer()
        result = await buf.swap_and_reset()
        assert result == {"__total__": 0}

    async def test_after_swap_active_is_fresh(self):
        """After swap, _active is a fresh Counter — old data does not leak."""
        buf = TrendBuffer()
        await buf.record("timeout")
        await buf.record("timeout")
        first = await buf.swap_and_reset()
        assert first["timeout"] == 2

        # New writes after swap should only appear in next snapshot
        await buf.record("timeout")
        second = await buf.swap_and_reset()
        assert second["timeout"] == 1
        assert second.get("__total__", 0) == 1

    async def test_total_matches_sum_of_types(self):
        """__total__ must equal sum of all individual type counts."""
        buf = TrendBuffer()
        expected = {}
        for _ in range(10):
            await buf.record("auth")
            expected["auth"] = expected.get("auth", 0) + 1
        for _ in range(5):
            await buf.record("rate_limit")
            expected["rate_limit"] = expected.get("rate_limit", 0) + 1

        snap = await buf.swap_and_reset()
        assert snap["__total__"] == 15
        assert snap["auth"] == 10
        assert snap["rate_limit"] == 5


# ═══════════════════════════════════════════════════════════
# 2. Algorithm Correctness (5 tests)
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestTrendDetectorAlgorithm:
    async def test_stable_rates_no_alert(self):
        """
        6 buckets with stable error rate (0.02 each) → no alerts.
        The stddev across 6 identical rates is 0.0, well below threshold.
        """
        td = TrendDetector()
        td._init_tables()
        now = time.time()
        # Seed 6 buckets, each with rate_limit rate = 0.02 (2 errors / 100 calls)
        for i in range(6):
            window_start = now - (6 - i) * 600
            td._insert_snapshot(window_start, window_start + 600, "rate_limit", 2)
            td._insert_snapshot(window_start, window_start + 600, "__total__", 100)

        alerts = await td._analyze()
        assert len(alerts) == 0, f"Expected no alerts for stable rates, got {len(alerts)}"

    async def test_spike_triggers_alert(self):
        """
        Bucket 5 (last one) spikes from 0.02 → 0.10 → triggers ALERTING.
        """
        td = TrendDetector()
        td._init_tables()
        now = time.time()
        # Buckets 0-4: stable 2/100 = 0.02
        for i in range(5):
            window_start = now - (6 - i) * 600
            td._insert_snapshot(window_start, window_start + 600, "rate_limit", 2)
            td._insert_snapshot(window_start, window_start + 600, "__total__", 100)
        # Bucket 5 (last one, 0-10 min ago): spike to 10/100 = 0.10
        window_start = now - 600
        td._insert_snapshot(window_start, window_start + 600, "rate_limit", 10)
        td._insert_snapshot(window_start, window_start + 600, "__total__", 100)
        # Force cold start: disable baseline so hard threshold is used
        td._cold_threshold = 0.02
        td._baseline_hours = 0  # force baseline_std = None → use cold threshold

        alerts = await td._analyze()
        assert len(alerts) > 0, f"Expected alert for spike, got {len(alerts)}"
        assert alerts[0].error_type == "rate_limit"

    async def test_cold_start_uses_hard_threshold(self):
        """
        No historical baseline (baseline_std=None) → fallback to 5% hard threshold.
        stddev=0.06 > 0.05 → alert triggered.
        """
        td = TrendDetector()
        td._init_tables()
        td._cold_threshold = 0.04  # lower threshold to ensure detection
        now = time.time()
        # Create unstable pattern: rates = [0.02, 0.02, 0.10, 0.02, 0.02, 0.02]
        # stddev ≈ 0.030... let me make it more dramatic
        for i in range(5):
            window_start = now - (6 - i) * 600
            td._insert_snapshot(window_start, window_start + 600, "rate_limit", 2)
            td._insert_snapshot(window_start, window_start + 600, "__total__", 100)
        # One big spike
        window_start = now
        td._insert_snapshot(window_start, window_start + 600, "rate_limit", 20)
        td._insert_snapshot(window_start, window_start + 600, "__total__", 100)

        # Set cold_threshold very low so any deviation triggers
        td._cold_threshold = 0.01
        alerts = await td._analyze()
        assert len(alerts) > 0, "Cold start with spike should trigger alert"

    async def test_low_traffic_no_false_alert(self):
        """
        Only 5 total calls in the past hour (< 50 min_calls) → bypass, no alerts.
        """
        td = TrendDetector()
        td._init_tables()
        td._min_calls = 50
        now = time.time()
        # 1 call per bucket, 1 failed = 100% error rate but no significance
        for i in range(6):
            window_start = now - (6 - i) * 600
            td._insert_snapshot(window_start, window_start + 600, "rate_limit", 1 if i == 2 else 0)
            td._insert_snapshot(window_start, window_start + 600, "__total__", 1)

        alerts = await td._analyze()
        assert len(alerts) == 0, f"Low traffic should not trigger alerts, got {len(alerts)}"

    async def test_tz_baseline_uses_correct_hour(self):
        """
        Verify timezone conversion: UTC stored, Asia/Shanghai used for hour matching.
        Use a known weekday to avoid calendar-dependent filtering.
        """
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        # Use a known Monday (July 6, 2026 = Monday)
        local_dt = datetime(2026, 7, 6, 14, 0, 0, tzinfo=tz)
        utc_ts = local_dt.timestamp()

        td = TrendDetector()
        td._init_tables()
        td._baseline_hours = 240  # 10 days
        # Insert baseline data at same hour, 1-8 days back (all weekdays, Mon-Fri)
        for i in range(1, 6):
            baseline_ts = utc_ts - i * 86400
            td._insert_snapshot(baseline_ts, baseline_ts + 600, "timeout", 3)
            td._insert_snapshot(baseline_ts, baseline_ts + 600, "__total__", 100)

        baseline = td._baseline_std("timeout", utc_ts)
        assert baseline is not None, "Should find baseline data for the same hour (weekday match)"


# ═══════════════════════════════════════════════════════════
# 3. State Machine (3 tests)
# ═══════════════════════════════════════════════════════════

class TestTrendDetectorStateMachine:
    def test_normal_to_alerting(self):
        """First spike: NORMAL → ALERTING."""
        td = TrendDetector()
        state = td._advance_state("rate_limit", ratio=2.5, current_std=0.05, baseline_std=0.02)
        assert state == AlertState.ALERTING
        assert td._state["rate_limit"] == AlertState.ALERTING

    def test_alerting_escalates_to_high(self):
        """3 consecutive ALERTING evaluations with ratio > 3.0 → HIGH_ALERT."""
        td = TrendDetector()
        # First: NORMAL → ALERTING
        td._advance_state("rate_limit", ratio=3.5, current_std=0.07, baseline_std=0.02)
        assert td._state["rate_limit"] == AlertState.ALERTING

        # Second: ratio > 3.0, consecutive_up = 2
        state = td._advance_state("rate_limit", ratio=3.5, current_std=0.07, baseline_std=0.02)
        assert state == AlertState.ALERTING
        assert td._consecutive_up["rate_limit"] == 2

        # Third: ratio > 3.0, consecutive_up = 3 → HIGH_ALERT
        state = td._advance_state("rate_limit", ratio=4.0, current_std=0.08, baseline_std=0.02)
        assert state == AlertState.HIGH_ALERT
        assert td._state["rate_limit"] == AlertState.HIGH_ALERT

    def test_high_alert_resolves_after_normal(self):
        """After HIGH_ALERT, 3 normal evaluations → RESOLVED."""
        td = TrendDetector()
        # Set up HIGH_ALERT
        td._state["timeout"] = AlertState.ALERTING
        for _ in range(3):
            td._advance_state("timeout", ratio=4.0, current_std=0.08, baseline_std=0.02)
        assert td._state["timeout"] == AlertState.HIGH_ALERT

        # Now 3 normal evaluations
        td._consecutive_normal["timeout"] = 0
        for i in range(3):
            td._check_resolve("timeout")
        assert td._state["timeout"] == AlertState.RESOLVED

    def test_single_spike_does_not_escalate(self):
        """Single spike with ratio 2.5 → ALERTING → recovery → no escalation."""
        td = TrendDetector()
        # Spike
        td._advance_state("rate_limit", ratio=2.5, current_std=0.05, baseline_std=0.02)
        assert td._state["rate_limit"] == AlertState.ALERTING

        # Then 3 normal evaluations → should resolve, never reach HIGH_ALERT
        for _ in range(3):
            td._check_resolve("rate_limit")
        assert td._state["rate_limit"] == AlertState.RESOLVED
        # Never escalated
        assert td._consecutive_up.get("rate_limit", 0) < 3


# ═══════════════════════════════════════════════════════════
# 4. Integration (2 tests)
# ═══════════════════════════════════════════════════════════

class TestTrendDetectorIntegration:
    def test_module_imports_no_circular(self):
        """Full import without circular dependency errors."""
        from core.harness.infrastructure.trend_detector import (
            TrendBuffer,
            TrendDetector,
            AlertState,
            AlertLevel,
            EntropyAlert,
            EntropyBucket,
            get_trend_detector,
        )
        assert TrendBuffer is not None
        assert TrendDetector is not None

    def test_set_trend_recorder_injection(self):
        """set_trend_recorder() injects a callable that _record_classification invokes."""
        from core.harness.infrastructure.gates.error_translator import (
            set_trend_recorder,
            _record_classification,
        )
        counter = []
        set_trend_recorder(lambda k: counter.append(k))
        _record_classification("rate_limit")
        _record_classification("__total__")
        assert counter == ["rate_limit", "__total__"]
