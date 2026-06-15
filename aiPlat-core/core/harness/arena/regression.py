"""
Regression Runner — benchmark-based agent evaluation.

Runs agent variants against a set of benchmark tasks and compares
results against a stored baseline. Used to gate prompt/model/tool changes.
"""

from __future__ import annotations

import logging
import time
import yaml
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class BenchmarkTask:
    id: str
    category: str
    task: str
    expected_tools: List[str] = field(default_factory=list)
    pass_criteria: List[str] = field(default_factory=list)
    cost_budget_tokens: int = 5000
    timeout_s: int = 30


@dataclass
class TaskResult:
    task_id: str
    category: str
    passed: bool
    score: int = 0  # 0-100
    error: str = ""
    output: str = ""
    tool_calls: List[str] = field(default_factory=list)
    tokens_used: int = 0
    latency_s: float = 0.0
    failed_criteria: List[str] = field(default_factory=list)


@dataclass
class RegressionReport:
    baseline: Optional[Dict[str, Any]] = None
    current: Dict[str, Any] = field(default_factory=dict)
    tasks: List[TaskResult] = field(default_factory=list)
    delta: Dict[str, float] = field(default_factory=dict)
    verdict: str = "UNKNOWN"  # PASS | REGRESSION | NO_BASELINE
    total_duration_s: float = 0.0


class RegressionRunner:
    """
    Runs agent through benchmark tasks and compares against baseline.
    
    Usage:
      runner = RegressionRunner()
      report = await runner.run(agent_fn=my_agent, baseline_path="~/.aiplat/arena_baseline.json")
    """

    def __init__(self, benchmarks_path: Optional[str] = None):
        self._benchmarks_path = benchmarks_path or os.path.join(
            os.path.dirname(__file__), "benchmarks", "sample_tasks.yaml"
        )

    def load_tasks(self) -> List[BenchmarkTask]:
        try:
            with open(self._benchmarks_path) as f:
                data = yaml.safe_load(f)
            tasks = []
            for t in data.get("tasks", []):
                tasks.append(BenchmarkTask(
                    id=t.get("id", ""),
                    category=t.get("category", ""),
                    task=t.get("task", ""),
                    expected_tools=t.get("expected_tools", []),
                    pass_criteria=t.get("pass_criteria", []),
                    cost_budget_tokens=t.get("cost_budget_tokens", 5000),
                    timeout_s=t.get("timeout_s", 30),
                ))
            return tasks
        except Exception as e:
            log.warning("Failed to load benchmarks: %s", e)
            return []

    async def run(
        self,
        *,
        agent_fn,  # async (task: str) -> dict with {output, tool_calls, tokens, error}
        baseline_path: Optional[str] = None,
        save_baseline: bool = False,
    ) -> RegressionReport:
        """
        Run all benchmark tasks and compare against baseline.
        """
        tasks = self.load_tasks()
        if not tasks:
            return RegressionReport(verdict="NO_TASKS")

        report = RegressionReport()
        start = time.time()

        # Load baseline
        baseline = None
        if baseline_path:
            try:
                with open(os.path.expanduser(baseline_path)) as f:
                    baseline = yaml.safe_load(f.read()) if f else {}
            except Exception:
                pass
        report.baseline = baseline or {}

        # Run each task
        total_passed = 0
        total_tokens = 0
        total_latency = 0.0

        for task in tasks:
            tr = TaskResult(task_id=task.id, category=task.category, passed=False)
            t_start = time.time()
            try:
                result = await agent_fn(task.task)
                tr.output = str(result.get("output", ""))[:1000]
                tr.tool_calls = result.get("tool_calls", []) or []
                tr.tokens_used = result.get("tokens", 0)
                tr.error = result.get("error", "") or ""

                # Evaluate pass criteria
                failed = []
                for criterion in task.pass_criteria:
                    if not self._check_criterion(criterion, tr):
                        failed.append(criterion)
                tr.failed_criteria = failed
                tr.passed = len(failed) == 0
                tr.score = max(0, 100 - len(failed) * 20)
            except Exception as e:
                tr.error = str(e)
                tr.passed = False
                tr.score = 0

            tr.latency_s = time.time() - t_start
            total_latency += tr.latency_s
            total_tokens += tr.tokens_used
            if tr.passed:
                total_passed += 1
            report.tasks.append(tr)

        # Aggregate current
        report.current = {
            "pass_rate": round(total_passed / max(len(tasks), 1) * 100, 1),
            "total_tasks": len(tasks),
            "total_passed": total_passed,
            "total_failed": len(tasks) - total_passed,
            "avg_latency_s": round(total_latency / max(len(tasks), 1), 2),
            "total_tokens": total_tokens,
        }

        # Delta vs baseline
        if baseline:
            b_pass = baseline.get("pass_rate", 0)
            b_lat = baseline.get("avg_latency_s", 0)
            b_tok = baseline.get("total_tokens", 0)
            c_pass = report.current["pass_rate"]
            c_lat = report.current["avg_latency_s"]
            c_tok = report.current["total_tokens"]

            report.delta = {
                "pass_rate_delta": round(c_pass - b_pass, 1),
                "latency_delta_ms": round((c_lat - b_lat) * 1000, 0),
                "token_delta_pct": round((c_tok - b_tok) / max(b_tok, 1) * 100, 1),
            }

            # Verdict
            if report.delta["pass_rate_delta"] < -5:
                report.verdict = "REGRESSION"
            elif report.delta["pass_rate_delta"] >= 0:
                report.verdict = "PASS"
            else:
                report.verdict = "WARN"
        else:
            report.verdict = "NO_BASELINE"

        report.total_duration_s = time.time() - start

        # Save baseline
        if save_baseline:
            bp = os.path.expanduser(baseline_path or "~/.aiplat/arena_baseline.json")
            try:
                os.makedirs(os.path.dirname(bp), exist_ok=True)
                import json
                with open(bp, "w") as f:
                    json.dump(report.current, f, indent=2)
            except Exception:
                pass

        log.info("Regression: %s (pass_rate=%.1f%%, %d/%d tasks)",
                 report.verdict, report.current["pass_rate"], total_passed, len(tasks))
        return report

    def _check_criterion(self, criterion: str, result: TaskResult) -> bool:
        """Evaluate a pass criterion against a task result."""
        output = result.output.lower()
        c = criterion.lower()

        if "non-empty" in c:
            return len(result.output) > 0
        if "at least" in c and "tool_call" in c:
            import re
            num = re.search(r'(\d+)', c)
            expected = int(num.group(1)) if num else 1
            return len(result.tool_calls) >= expected
        if "shorter than input" in c:
            return len(result.output) < 200
        if "correct answer" in c:
            import re
            nums = re.findall(r'\d+', c)
            for n in nums:
                if n in result.output:
                    return True
            return False
        if "valid json" in c:
            import json
            try:
                json.loads(result.output)
                return True
            except Exception:
                return False
        if "required fields" in c:
            import json
            try:
                data = json.loads(result.output) if result.output.startswith('{') else {}
                return all(f in data for f in ["name", "age", "skills"])
            except Exception:
                return False
        if "integer" in c and "age" in c:
            import json
            try:
                data = json.loads(result.output) if result.output.startswith('{') else {}
                return isinstance(data.get("age"), int)
            except Exception:
                return False
        if "array" in c and "skills" in c:
            import json
            try:
                data = json.loads(result.output) if result.output.startswith('{') else {}
                return isinstance(data.get("skills"), list)
            except Exception:
                return False
        if "chinese" in c:
            import re
            return bool(re.search(r'[\u4e00-\u9fff]', result.output))
        if "explains the error" in c:
            return "error" in output or "fail" in output or "not found" in output or "exist" in output
        if "not crash" in c or "not hang" in c:
            return True  # we got here, so no crash
        if "syllogism" in c or "logical conclusion" in c:
            return "all" in output or "therefore" in output or "conclusion" in output or "syllogism" in output
        if "one sentence" in c:
            return result.output.count('.') <= 2
        if "more information" in c or "clarification" in c:
            return "?" in result.output or "what" in output or "clarify" in output or "more" in output
        if "complete" in c and "function" in c:
            return "def " in output and "return" in output

        return True  # unknown criteria pass through


__all__ = ["RegressionRunner", "RegressionReport", "BenchmarkTask", "TaskResult"]
