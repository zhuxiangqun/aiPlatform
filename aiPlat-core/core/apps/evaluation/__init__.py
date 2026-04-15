"""
Evaluation Module

Agent evaluation system with benchmarks, grading, and regression detection.
"""

from .types import (
    TraceGrade,
    TaskResult,
    BenchmarkResult,
    AgentTrace,
    RegressionResult,
    EvaluationConfig,
)
from .benchmarks import Benchmark, Task, run_benchmark, get_builtin_benchmarks
from .grader import LLmGrader, grade_trace
from .tracker import TraceTracker, track_execution
from .regression import RegressionDetector, check_regression
from .reporter import ResultReporter, generate_report

__all__ = [
    "TraceGrade",
    "TaskResult",
    "BenchmarkResult",
    "AgentTrace",
    "RegressionResult",
    "EvaluationConfig",
    "Benchmark",
    "Task",
    "run_benchmark",
    "get_builtin_benchmarks",
    "LLmGrader",
    "grade_trace",
    "TraceTracker",
    "track_execution",
    "RegressionDetector",
    "check_regression",
    "ResultReporter",
    "generate_report",
]