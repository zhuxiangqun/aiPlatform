"""
Benchmark Module

Defines evaluation benchmarks and task definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, TYPE_CHECKING
import asyncio


if TYPE_CHECKING:
    from .types import TaskResult, BenchmarkResult


@dataclass
class Task:
    """Single evaluation task"""
    id: str
    prompt: str
    expected_tools: List[str] = field(default_factory=list)
    success_criteria: str = ""
    category: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Benchmark:
    """Benchmark definition"""
    name: str
    description: str
    tasks: List[Task]
    metric: str = "pass_at_1"
    tags: List[str] = field(default_factory=list)
    
    def get_tasks_by_category(self, category: str) -> List[Task]:
        return [t for t in self.tasks if t.category == category]
    
    @property
    def task_count(self) -> int:
        return len(self.tasks)


class AgentExecutor:
    """Protocol for agent execution"""
    
    async def execute(self, prompt: str) -> Dict[str, Any]:
        """Execute agent with prompt and return result"""
        raise NotImplementedError


async def run_benchmark(
    benchmark: "Benchmark",
    executor: "AgentExecutor",
    max_retries: int = 3,
    timeout_ms: int = 60000,
    pass_at_k: int = 3
) -> "BenchmarkResult":
    """Run benchmark against agent executor"""
    from .types import TaskResult, BenchmarkResult

    task_results: List[TaskResult] = []
    
    for task in benchmark.tasks:
        for attempt in range(pass_at_k):
            try:
                result = await asyncio.wait_for(
                    executor.execute(task.prompt),
                    timeout=timeout_ms / 1000
                )
                
                success = _evaluate_success(result, task)
                
                task_result = TaskResult(
                    task_id=task.id,
                    success=success,
                    latency_ms=result.get("latency_ms", 0),
                    tokens_used=result.get("tokens_used", 0),
                    tool_calls=result.get("tool_calls", []),
                    metadata={"attempt": attempt + 1}
                )
                
                if success or attempt == pass_at_k - 1:
                    task_results.append(task_result)
                    break
                    
            except asyncio.TimeoutError:
                task_results.append(TaskResult(
                    task_id=task.id,
                    success=False,
                    latency_ms=timeout_ms,
                    tokens_used=0,
                    error="timeout"
                ))
                break
            except Exception as e:
                task_results.append(TaskResult(
                    task_id=task.id,
                    success=False,
                    latency_ms=0,
                    tokens_used=0,
                    error=str(e)
                ))
                break
    
    passed = sum(1 for r in task_results if r.success)
    total = len(task_results)
    
    return BenchmarkResult(
        benchmark_name=benchmark.name,
        total_tasks=total,
        passed_tasks=passed,
        pass_at_1=passed / total if total > 0 else 0.0,
        pass_at_3=passed / total if total > 0 else 0.0,
        pass_at_k=passed / total if total > 0 else 0.0,
        avg_latency_ms=sum(r.latency_ms for r in task_results) / total if total > 0 else 0.0,
        avg_tokens=sum(r.tokens_used for r in task_results) / total if total > 0 else 0,
        task_results=task_results
    )


def _evaluate_success(result: Dict[str, Any], task: Task) -> bool:
    """Evaluate if task was successful"""
    if task.success_criteria:
        return result.get("response", "") and task.success_criteria.lower() in result["response"].lower()
    return result.get("success", False)


BUILTIN_BENCHMARKS = {
    "code-review": Benchmark(
        name="code-review",
        description="Code review tasks",
        tasks=[
            Task(id=f"cr-{i}", prompt=f"Review this code change #{i}", category="review")
            for i in range(20)
        ]
    ),
    "bug-fix": Benchmark(
        name="bug-fix",
        description="Bug fix tasks",
        tasks=[
            Task(id=f"bf-{i}", prompt=f"Fix this bug #{i}", category="fix")
            for i in range(30)
        ]
    ),
    "refactor": Benchmark(
        name="refactor",
        description="Code refactoring tasks",
        tasks=[
            Task(id=f"rf-{i}", prompt=f"Refactor this code #{i}", category="refactor")
            for i in range(15)
        ]
    ),
    "test-write": Benchmark(
        name="test-write",
        description="Test writing tasks",
        tasks=[
            Task(id=f"tw-{i}", prompt=f"Write tests for this code #{i}", category="test")
            for i in range(25)
        ]
    ),
    "doc-gen": Benchmark(
        name="doc-gen",
        description="Documentation generation tasks",
        tasks=[
            Task(id=f"dg-{i}", prompt=f"Generate docs for this code #{i}", category="docs")
            for i in range(20)
        ]
    ),
}


def get_builtin_benchmarks() -> Dict[str, Benchmark]:
    """Get all builtin benchmarks"""
    return BUILTIN_BENCHMARKS.copy()


def get_benchmark(name: str) -> Optional[Benchmark]:
    """Get benchmark by name"""
    return BUILTIN_BENCHMARKS.get(name)


__all__ = [
    "Task",
    "Benchmark",
    "AgentExecutor",
    "run_benchmark",
    "get_builtin_benchmarks",
    "get_benchmark",
]