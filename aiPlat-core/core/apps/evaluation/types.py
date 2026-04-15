"""
Evaluation Module Types
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
from datetime import datetime


class TraceGrade(Enum):
    """Trace quality grades"""
    GRADE_A = "A"
    GRADE_B = "B"
    GRADE_C = "C"
    GRADE_D = "D"


@dataclass
class TaskResult:
    """Result of a single task evaluation"""
    task_id: str
    success: bool
    latency_ms: int
    tokens_used: int
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    grade: Optional[TraceGrade] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """Result of benchmark execution"""
    benchmark_name: str
    total_tasks: int
    passed_tasks: int
    pass_at_1: float
    pass_at_3: float
    pass_at_k: float
    avg_latency_ms: float
    avg_tokens: int
    task_results: List[TaskResult] = field(default_factory=list)
    executed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def success_rate(self) -> float:
        return self.passed_tasks / self.total_tasks if self.total_tasks > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark_name": self.benchmark_name,
            "total_tasks": self.total_tasks,
            "passed_tasks": self.passed_tasks,
            "pass_at_1": self.pass_at_1,
            "pass_at_3": self.pass_at_3,
            "pass_at_k": self.pass_at_k,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_tokens": self.avg_tokens,
            "success_rate": self.success_rate,
            "executed_at": self.executed_at
        }


@dataclass
class AgentTrace:
    """Agent execution trace"""
    session_id: str
    task_id: str
    prompt: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    final_response: str = ""
    success: bool = False
    latency_ms: int = 0
    tokens_used: int = 0
    quality_score: float = 0.0
    safety_score: float = 0.0
    tool_accuracy: float = 0.0
    grade: Optional[TraceGrade] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "prompt": self.prompt,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
            "final_response": self.final_response,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "quality_score": self.quality_score,
            "safety_score": self.safety_score,
            "tool_accuracy": self.tool_accuracy,
            "grade": self.grade.value if self.grade else None,
            "created_at": self.created_at
        }


@dataclass
class RegressionResult:
    """Result of regression detection"""
    has_regression: bool
    current_result: BenchmarkResult
    baseline_result: BenchmarkResult
    changes: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_regression": self.has_regression,
            "current_result": self.current_result.to_dict(),
            "baseline_result": self.baseline_result.to_dict(),
            "changes": self.changes,
            "recommendations": self.recommendations
        }


@dataclass
class EvaluationConfig:
    """Configuration for evaluation"""
    benchmark_name: str
    max_retries: int = 3
    timeout_ms: int = 60000
    pass_at_k: int = 3
    enable_llm_judge: bool = True
    baseline_path: Optional[str] = None


__all__ = [
    "TraceGrade",
    "TaskResult",
    "BenchmarkResult",
    "AgentTrace",
    "RegressionResult",
    "EvaluationConfig",
]