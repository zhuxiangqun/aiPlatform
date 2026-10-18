"""Half-open circuit allows one probe, not a stampede."""

from core.harness.infrastructure.circuit_breaker import BaseCircuitBreaker
from core.harness.syscalls.llm import LLMCircuitBreaker


def test_base_half_open_single_probe():
    cb = BaseCircuitBreaker(failure_threshold=1, recovery_timeout=0)
    cb.failure()
    assert cb._state == "open"
    cb._open_ts = 0
    assert cb.allow() is True
    assert cb._state == "half_open"
    assert cb.allow() is False
    cb.success()
    assert cb._state == "closed"
    assert cb.allow() is True


def test_llm_half_open_single_probe():
    cb = LLMCircuitBreaker(failure_threshold=1, recovery_timeout=0)
    cb.record_failure()
    assert cb._state == "open"
    cb._open_ts = 0
    assert cb.allow_request() is True
    assert cb.allow_request() is False
    cb.record_success()
    assert cb._state == "closed"
    assert cb.allow_request() is True
