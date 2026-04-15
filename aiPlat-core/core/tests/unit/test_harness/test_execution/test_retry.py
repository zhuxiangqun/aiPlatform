"""
Tests for Execution Retry module.

Tests cover:
- RetryConfig
- RetryManager
- ExponentialBackoff
- LinearBackoff
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from harness.execution.retry import (
    RetryConfig,
    RetryManager,
    ExponentialBackoff,
    LinearBackoff,
    RetryStrategy,
    create_retry_manager,
)


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""
    
    def test_retry_config_defaults(self):
        """Test RetryConfig default values."""
        config = RetryConfig()
        
        assert config.max_attempts == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
    
    def test_retry_config_custom(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            max_attempts=5,
            initial_delay=0.5,
            max_delay=120.0,
            exponential_base=3.0,
            jitter=False,
        )
        
        assert config.max_attempts == 5
        assert config.initial_delay == 0.5
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0
        assert config.jitter is False


class TestExponentialBackoff:
    """Tests for ExponentialBackoff strategy."""
    
    def test_exponential_backoff_init(self):
        """Test ExponentialBackoff initialization."""
        config = RetryConfig()
        backoff = ExponentialBackoff(config)
        
        assert backoff._config == config
    
    def test_exponential_backoff_first_attempt(self):
        """Test delay calculation for first attempt."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0, jitter=False)
        backoff = ExponentialBackoff(config)
        
        delay = backoff.get_delay(attempt=0)
        
        # First attempt: initial_delay * (base ^ 0) = 1.0 * 1 = 1.0
        assert delay == 1.0
    
    def test_exponential_backoff_second_attempt(self):
        """Test delay calculation for second attempt."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0, jitter=False)
        backoff = ExponentialBackoff(config)
        
        delay = backoff.get_delay(attempt=1)
        
        # Second attempt: 1.0 * (2 ^ 1) = 2.0
        assert delay == 2.0
    
    def test_exponential_backoff_respects_max_delay(self):
        """Test that delay respects max_delay cap."""
        config = RetryConfig(
            initial_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=False,
        )
        backoff = ExponentialBackoff(config)
        
        delay = backoff.get_delay(attempt=10)
        
        # Should cap at max_delay
        assert delay <= 5.0


class TestLinearBackoff:
    """Tests for LinearBackoff strategy."""
    
    def test_linear_backoff_init(self):
        """Test LinearBackoff initialization."""
        config = RetryConfig()
        backoff = LinearBackoff(config)
        
        assert backoff._config == config
    
    def test_linear_backoff_first_attempt(self):
        """Test delay calculation for first attempt."""
        config = RetryConfig(initial_delay=1.0, jitter=False)
        backoff = LinearBackoff(config)
        
        delay = backoff.get_delay(attempt=1)
        
        # Linear: initial_delay * attempt = 1.0 * 1 = 1.0
        assert delay == 1.0
    
    def test_linear_backoff_respects_max_delay(self):
        """Test that delay respects max_delay cap."""
        config = RetryConfig(
            initial_delay=1.0,
            max_delay=5.0,
            jitter=False,
        )
        backoff = LinearBackoff(config)
        
        delay = backoff.get_delay(attempt=10)
        
        # Should cap at max_delay
        assert delay <= 5.0


class TestRetryManager:
    """Tests for RetryManager."""
    
    def test_retry_manager_init(self):
        """Test RetryManager initialization."""
        config = RetryConfig(max_attempts=5)
        manager = RetryManager(config)
        
        assert manager._config.max_attempts == 5
    
    def test_retry_manager_default_config(self):
        """Test RetryManager with default config."""
        manager = RetryManager()
        
        assert manager._config.max_attempts == 3
    
    @pytest.mark.asyncio
    async def test_retry_success_no_retry(self):
        """Test successful operation doesn't retry."""
        manager = RetryManager()
        
        call_count = 0
        
        async def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await manager.execute(successful_operation)
        
        assert result == "success"
        assert call_count == 1


class TestCreateRetryManager:
    """Tests for create_retry_manager factory."""
    
    def test_create_with_default_config(self):
        """Test creating RetryManager with default config."""
        manager = create_retry_manager()
        
        assert manager._config.max_attempts == 3
    
    def test_create_with_custom_attempts(self):
        """Test creating RetryManager with custom max_attempts."""
        manager = create_retry_manager(max_attempts=10)
        
        assert manager._config.max_attempts == 10