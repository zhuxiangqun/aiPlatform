"""
Execution Policy Module

Defines execution policies and strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class PolicyType(Enum):
    """Policy type enumeration"""
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    BUDGET = "budget"
    MAX_STEPS = "max_steps"
    CUSTOM = "custom"


@dataclass
class PolicyConfig:
    """Policy configuration"""
    policy_type: PolicyType
    enabled: bool = True
    threshold: float = 0.0
    action: str = "stop"  # stop, warn, retry
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyResult:
    """Policy evaluation result"""
    passed: bool
    action: str
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class IPolicy(ABC):
    """
    Policy interface
    """

    @abstractmethod
    def evaluate(self, context: Dict[str, Any]) -> PolicyResult:
        """Evaluate policy"""
        pass

    @abstractmethod
    def get_config(self) -> PolicyConfig:
        """Get policy configuration"""
        pass


class TimeoutPolicy(IPolicy):
    """Timeout policy"""

    def __init__(self, timeout: float, action: str = "stop"):
        self._config = PolicyConfig(
            policy_type=PolicyType.TIMEOUT,
            threshold=timeout,
            action=action,
        )

    def evaluate(self, context: Dict[str, Any]) -> PolicyResult:
        elapsed = context.get("elapsed_time", 0)
        timeout = self._config.threshold
        
        if elapsed > timeout:
            return PolicyResult(
                passed=False,
                action=self._config.action,
                message=f"Timeout exceeded: {elapsed}s > {timeout}s",
                metadata={"elapsed": elapsed, "threshold": timeout}
            )
        
        return PolicyResult(passed=True, action="continue")

    def get_config(self) -> PolicyConfig:
        return self._config


class BudgetPolicy(IPolicy):
    """Budget policy for token usage"""

    def __init__(self, budget: float, action: str = "stop"):
        self._config = PolicyConfig(
            policy_type=PolicyType.BUDGET,
            threshold=budget,
            action=action,
        )

    def evaluate(self, context: Dict[str, Any]) -> PolicyResult:
        used = context.get("used_budget", 0)
        remaining = context.get("remaining_budget", 1.0)
        
        if remaining <= 0 or used >= self._config.threshold:
            return PolicyResult(
                passed=False,
                action=self._config.action,
                message=f"Budget exhausted: {used}/{self._config.threshold}",
                metadata={"used": used, "threshold": self._config.threshold}
            )
        
        return PolicyResult(passed=True, action="continue")

    def get_config(self) -> PolicyConfig:
        return self._config


class MaxStepsPolicy(IPolicy):
    """Max steps policy"""

    def __init__(self, max_steps: int, action: str = "stop"):
        self._config = PolicyConfig(
            policy_type=PolicyType.MAX_STEPS,
            threshold=float(max_steps),
            action=action,
        )

    def evaluate(self, context: Dict[str, Any]) -> PolicyResult:
        current_step = context.get("current_step", 0)
        max_steps = int(self._config.threshold)
        
        if current_step >= max_steps:
            return PolicyResult(
                passed=False,
                action=self._config.action,
                message=f"Max steps reached: {current_step} >= {max_steps}",
                metadata={"step": current_step, "max": max_steps}
            )
        
        return PolicyResult(passed=True, action="continue")

    def get_config(self) -> PolicyConfig:
        return self._config


class RateLimitPolicy(IPolicy):
    """Rate limit policy"""

    def __init__(self, max_calls: int, window_seconds: float, action: str = "wait"):
        self._config = PolicyConfig(
            policy_type=PolicyType.RATE_LIMIT,
            threshold=float(max_calls),
            action=action,
        )
        self._window = window_seconds
        self._calls: List[float] = []

    def evaluate(self, context: Dict[str, Any]) -> PolicyResult:
        import time
        now = time.time()
        
        # Clean old calls
        self._calls = [t for t in self._calls if now - t < self._window]
        
        max_calls = int(self._config.threshold)
        
        if len(self._calls) >= max_calls:
            wait_time = self._window - (now - self._calls[0])
            return PolicyResult(
                passed=False,
                action=self._config.action,
                message=f"Rate limit reached, wait {wait_time:.1f}s",
                metadata={"calls": len(self._calls), "max": max_calls, "wait": wait_time}
            )
        
        self._calls.append(now)
        return PolicyResult(passed=True, action="continue")

    def get_config(self) -> PolicyConfig:
        return self._config


class PolicyEngine:
    """
    Policy engine for managing multiple policies
    """

    def __init__(self):
        self._policies: List[IPolicy] = []
        self._enabled = True

    def add_policy(self, policy: IPolicy) -> "PolicyEngine":
        """Add a policy"""
        self._policies.append(policy)
        return self

    def evaluate_all(self, context: Dict[str, Any]) -> List[PolicyResult]:
        """Evaluate all policies"""
        if not self._enabled:
            return [PolicyResult(passed=True, action="continue")]
        
        results = []
        for policy in self._policies:
            result = policy.evaluate(context)
            results.append(result)
            
            # Stop on first failure with stop action
            if not result.passed and result.action == "stop":
                break
        
        return results

    def evaluate_and_raise(self, context: Dict[str, Any]) -> None:
        """Evaluate policies and raise on failure"""
        results = self.evaluate_all(context)
        
        for result in results:
            if not result.passed and result.action == "stop":
                raise PolicyViolationError(result.message)

    def enable(self) -> None:
        """Enable policy engine"""
        self._enabled = True

    def disable(self) -> None:
        """Disable policy engine"""
        self._enabled = False


class PolicyViolationError(Exception):
    """Policy violation error"""
    pass


def create_policy_engine(
    timeout: Optional[float] = None,
    max_steps: Optional[int] = None,
    budget: Optional[float] = None
) -> PolicyEngine:
    """
    Create policy engine with common policies
    
    Args:
        timeout: Timeout in seconds
        max_steps: Maximum steps
        budget: Token budget (0-1)
        
    Returns:
        PolicyEngine: Configured policy engine
    """
    engine = PolicyEngine()
    
    if timeout:
        engine.add_policy(TimeoutPolicy(timeout))
    
    if max_steps:
        engine.add_policy(MaxStepsPolicy(max_steps))
    
    if budget:
        engine.add_policy(BudgetPolicy(budget))
    
    return engine