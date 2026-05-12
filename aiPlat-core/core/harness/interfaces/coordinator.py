"""
Coordinator Types — Shared data types for multi-agent coordination.

ICoordinator interface has been removed (zero implementors).
Use Coordination Patterns (harness/coordination/patterns/) directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class CoordinationResult:
    """Multi-agent coordination result"""
    success: bool
    results: List[Any] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoordinationConfig:
    """Coordinator configuration"""
    max_agents: int = 5
    timeout: int = 60
    convergence_threshold: float = 0.8
    max_rounds: int = 10
    metadata: Dict[str, Any] = field(default_factory=dict)
