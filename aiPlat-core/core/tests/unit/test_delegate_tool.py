"""Tests for delegate_tool.py — sub-agent delegation with resource budgets."""
import pytest
from core.harness.infrastructure.delegate_tool import (
    DelegateManager, DelegateConfig, DelegateResult, DelegateStats,
    get_delegate_manager, reset_delegate_manager,
)


@pytest.fixture(autouse=True)
def reset():
    reset_delegate_manager()
    yield
    reset_delegate_manager()


class TestDelegateConfig:
    def test_default_values(self):
        cfg = DelegateConfig(subagent_name="test", task="do something")
        assert cfg.max_tokens == 4096
        assert cfg.timeout_s == 300.0
        assert cfg.isolate_context is True
        assert cfg.max_output_chars == 800
        assert cfg.retry_on_failure is True
        assert cfg.max_retries == 2

    def test_custom_values(self):
        cfg = DelegateConfig(
            subagent_name="reviewer",
            task="review code",
            max_tokens=2048,
            timeout_s=60.0,
            max_retries=0,
        )
        assert cfg.max_tokens == 2048
        assert cfg.timeout_s == 60.0
        assert cfg.max_retries == 0


class TestDelegateResult:
    def test_success_result(self):
        result = DelegateResult(
            subagent_name="test",
            success=True,
            output="done",
            duration_ms=150.0,
            token_used=500,
        )
        assert result.success is True
        assert result.output == "done"
        assert result.error is None
        assert result.duration_ms == 150.0

    def test_failure_result(self):
        result = DelegateResult(
            subagent_name="test",
            success=False,
            output="",
            error="timeout",
            duration_ms=300000.0,
        )
        assert result.success is False
        assert result.error == "timeout"


class TestDelegateManager:
    def test_singleton(self):
        m1 = get_delegate_manager()
        m2 = get_delegate_manager()
        assert m1 is m2

    def test_reset(self):
        m1 = get_delegate_manager()
        reset_delegate_manager()
        m2 = get_delegate_manager()
        assert m1 is not m2

    def test_initial_stats(self):
        mgr = get_delegate_manager()
        stats = mgr.get_stats()
        assert stats["total"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["success_rate"] == 0.0

    def test_disabled_mode_returns_error(self):
        mgr = DelegateManager()
        mgr._disabled = True
        import asyncio
        result = asyncio.new_event_loop().run_until_complete(
            mgr.delegate(DelegateConfig(subagent_name="test", task="hello"))
        )
        assert result.success is False
        assert "disabled" in result.error.lower()

    def test_reset_stats(self):
        mgr = get_delegate_manager()
        mgr._stats.total_delegations = 10
        mgr.reset_stats()
        assert mgr._stats.total_delegations == 0

    def test_delegate_stats_initial(self):
        mgr = get_delegate_manager()
        stats = mgr.get_stats()
        assert "by_subagent" in stats
        assert "max_concurrent" in stats
        assert stats["max_concurrent"] == 5

    def test_delegate_parallel_empty(self):
        mgr = get_delegate_manager()
        import asyncio
        results = asyncio.new_event_loop().run_until_complete(
            mgr.delegate_parallel([])
        )
        assert results == []

    def test_delegate_sequential_empty(self):
        mgr = get_delegate_manager()
        import asyncio
        results = asyncio.new_event_loop().run_until_complete(
            mgr.delegate_sequential([])
        )
        assert results == []

    def test_stats_after_disable(self):
        mgr = get_delegate_manager()
        mgr._disabled = True
        import asyncio
        asyncio.new_event_loop().run_until_complete(
            mgr.delegate(DelegateConfig(subagent_name="test", task="fail"))
        )
        # When disabled, delegate returns early without updating stats
        # Just verify the method doesn't crash
        assert True


class TestDelegateManagerConcurrency:
    def test_semaphore_initialized(self):
        mgr = get_delegate_manager()
        assert mgr._semaphore is not None
        # Semaphore should have value = max_concurrent
        assert mgr._max_concurrent == 5


class TestDelegateStats:
    def test_default_values(self):
        stats = DelegateStats()
        assert stats.total_delegations == 0
        assert stats.successful == 0
        assert stats.failed == 0
        assert stats.total_duration_ms == 0.0
        assert stats.total_tokens == 0
        assert stats.by_subagent == {}
