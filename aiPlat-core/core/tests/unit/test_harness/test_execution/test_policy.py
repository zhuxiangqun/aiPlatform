"""
Tests for Execution Policy module.

Tests cover:
- PolicyType enum
- PolicyConfig
- TimeoutPolicy
- BudgetPolicy
- MaxStepsPolicy
- RateLimitPolicy
- PolicyEngine
"""

import pytest
from unittest.mock import MagicMock

from harness.execution.policy import (
    PolicyType,
    PolicyConfig,
    PolicyResult,
    IPolicy,
    TimeoutPolicy,
    BudgetPolicy,
    MaxStepsPolicy,
    RateLimitPolicy,
    PolicyEngine,
    PolicyViolationError,
    create_policy_engine,
)


class TestPolicyType:
    """Tests for PolicyType enum."""
    
    def test_policy_type_values(self):
        """Test PolicyType enum values."""
        assert PolicyType.TIMEOUT.value == "timeout"
        assert PolicyType.BUDGET.value == "budget"
        assert PolicyType.MAX_STEPS.value == "max_steps"
        assert PolicyType.RATE_LIMIT.value == "rate_limit"
        assert PolicyType.CUSTOM.value == "custom"


class TestPolicyConfig:
    """Tests for PolicyConfig."""
    
    def test_policy_config_defaults(self):
        """Test PolicyConfig default values."""
        config = PolicyConfig(policy_type=PolicyType.TIMEOUT)
        
        assert config.policy_type == PolicyType.TIMEOUT
        assert config.enabled is True
        assert config.threshold == 0.0
        assert config.action == "stop"
    
    def test_policy_config_custom(self):
        """Test PolicyConfig with custom values."""
        config = PolicyConfig(
            policy_type=PolicyType.TIMEOUT,
            threshold=60.0,
            action="warn",
            enabled=False,
        )
        
        assert config.threshold == 60.0
        assert config.action == "warn"
        assert config.enabled is False


class TestPolicyResult:
    """Tests for PolicyResult."""
    
    def test_policy_result_pass(self):
        """Test PolicyResult for passing policy."""
        result = PolicyResult(passed=True, action="continue")
        
        assert result.passed is True
        assert result.action == "continue"
    
    def test_policy_result_fail(self):
        """Test PolicyResult for failing policy."""
        result = PolicyResult(
            passed=False,
            action="stop",
            message="Policy violated"
        )
        
        assert result.passed is False
        assert result.action == "stop"
        assert "Policy violated" in result.message


class TestTimeoutPolicy:
    """Tests for TimeoutPolicy."""
    
    def test_timeout_policy_init(self):
        """Test TimeoutPolicy initialization."""
        policy = TimeoutPolicy(timeout=60)
        
        assert policy._config.threshold == 60
        assert policy._config.policy_type == PolicyType.TIMEOUT
    
    def test_timeout_policy_evaluate_within_limit(self):
        """Test evaluation within timeout limit."""
        policy = TimeoutPolicy(timeout=60)
        
        result = policy.evaluate({"elapsed_time": 30})
        
        assert result.passed is True
        assert result.action == "continue"
    
    def test_timeout_policy_evaluate_exceeded(self):
        """Test evaluation when timeout exceeded."""
        policy = TimeoutPolicy(timeout=60)
        
        result = policy.evaluate({"elapsed_time": 90})
        
        assert result.passed is False
        assert result.action == "stop"
    
    def test_timeout_policy_get_config(self):
        """Test getting policy configuration."""
        policy = TimeoutPolicy(timeout=30)
        
        config = policy.get_config()
        
        assert config.threshold == 30
        assert config.policy_type == PolicyType.TIMEOUT


class TestBudgetPolicy:
    """Tests for BudgetPolicy."""
    
    def test_budget_policy_init(self):
        """Test BudgetPolicy initialization."""
        policy = BudgetPolicy(budget=100.0)
        
        assert policy._config.threshold == 100.0
        assert policy._config.policy_type == PolicyType.BUDGET
    
    def test_budget_policy_evaluate_within_budget(self):
        """Test evaluation within budget."""
        policy = BudgetPolicy(budget=100.0)
        
        result = policy.evaluate({
            "used_budget": 50.0,
            "remaining_budget": 0.5,
        })
        
        assert result.passed is True
    
    def test_budget_policy_evaluate_exceeded(self):
        """Test evaluation when budget exceeded."""
        policy = BudgetPolicy(budget=100.0)
        
        result = policy.evaluate({
            "used_budget": 150.0,
            "remaining_budget": 0.0,
        })
        
        assert result.passed is False


class TestMaxStepsPolicy:
    """Tests for MaxStepsPolicy."""
    
    def test_max_steps_policy_init(self):
        """Test MaxStepsPolicy initialization."""
        policy = MaxStepsPolicy(max_steps=10)
        
        assert policy._config.threshold == 10
        assert policy._config.policy_type == PolicyType.MAX_STEPS
    
    def test_max_steps_evaluate_within_limit(self):
        """Test evaluation within max steps."""
        policy = MaxStepsPolicy(max_steps=10)
        
        result = policy.evaluate({"current_step": 5})
        
        assert result.passed is True
    
    def test_max_steps_evaluate_exceeded(self):
        """Test evaluation when max steps exceeded."""
        policy = MaxStepsPolicy(max_steps=10)
        
        result = policy.evaluate({"current_step": 15})
        
        assert result.passed is False


class TestRateLimitPolicy:
    """Tests for RateLimitPolicy."""
    
    def test_rate_limit_policy_init(self):
        """Test RateLimitPolicy initialization."""
        policy = RateLimitPolicy(max_calls=100, window_seconds=60)
        
        assert policy._config.threshold == 100
        assert policy._config.policy_type == PolicyType.RATE_LIMIT
    
    def test_rate_limit_evaluate_within_limit(self):
        """Test evaluation within rate limit."""
        policy = RateLimitPolicy(max_calls=100, window_seconds=60)
        
        result = policy.evaluate({"request_count": 50})
        
        assert result.passed is True
    
    def test_rate_limit_evaluate_exceeded(self):
        """Test evaluation when rate limit exceeded."""
        policy = RateLimitPolicy(max_calls=2, window_seconds=60)
        
        # Make calls to exceed limit
        policy.evaluate({})  # First call
        policy.evaluate({})  # Second call
        result = policy.evaluate({})  # Third call should fail
        
        assert result.passed is False


class TestPolicyEngine:
    """Tests for PolicyEngine."""
    
    def test_policy_engine_init(self):
        """Test PolicyEngine initialization."""
        engine = PolicyEngine()
        
        assert engine._policies == []
    
    def test_policy_engine_add_policy(self):
        """Test adding policy to engine."""
        engine = PolicyEngine()
        policy = TimeoutPolicy(timeout=60)
        
        engine.add_policy(policy)
        
        assert len(engine._policies) == 1
    
    def test_policy_engine_evaluate_all_passing(self):
        """Test evaluating all policies passing."""
        engine = PolicyEngine()
        engine.add_policy(TimeoutPolicy(timeout=60))
        engine.add_policy(MaxStepsPolicy(max_steps=10))
        
        results = engine.evaluate_all({
            "elapsed_time": 30,
            "current_step": 5,
        })
        
        assert all(r.passed for r in results)
    
    def test_policy_engine_evaluate_all_one_failing(self):
        """Test evaluating with one policy failing."""
        engine = PolicyEngine()
        engine.add_policy(TimeoutPolicy(timeout=60))
        engine.add_policy(MaxStepsPolicy(max_steps=10))
        
        results = engine.evaluate_all({
            "elapsed_time": 90,  # Exceeds timeout
            "current_step": 5,
        })
        
        assert any(not r.passed for r in results)
    
    def test_policy_engine_get_config(self):
        """Test getting engine configuration."""
        engine = PolicyEngine()
        
        # Add a policy
        engine.add_policy(TimeoutPolicy(timeout=60))
        
        # Engine should have policies
        assert len(engine._policies) == 1


class TestCreatePolicyEngine:
    """Tests for create_policy_engine factory."""
    
    def test_create_policy_engine_default(self):
        """Test creating PolicyEngine with defaults."""
        engine = create_policy_engine()
        
        assert engine is not None
    
    def test_create_policy_engine_adds_policies(self):
        """Test creating PolicyEngine and adding policies."""
        engine = create_policy_engine()
        engine.add_policy(TimeoutPolicy(timeout=60))
        engine.add_policy(MaxStepsPolicy(max_steps=10))
        
        assert len(engine._policies) == 2