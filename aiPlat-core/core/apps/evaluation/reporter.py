"""
Result Reporter Module

Generates evaluation reports in various formats.
"""

from typing import Dict, Any, List
from datetime import datetime
from .types import BenchmarkResult, RegressionResult


class ResultReporter:
    """Generates evaluation reports"""
    
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
    
    def add_result(self, result: BenchmarkResult):
        """Add result to history"""
        self.history.append(result.to_dict())
    
    def add_regression_result(self, result: RegressionResult):
        """Add regression result to history"""
        self.history.append({
            "type": "regression",
            "timestamp": datetime.now().isoformat(),
            **result.to_dict()
        })
    
    def generate_text(self, result: BenchmarkResult) -> str:
        """Generate text report"""
        lines = [
            f"Benchmark: {result.benchmark_name}",
            f"执行时间: {result.executed_at}",
            "",
            "=== 结果摘要 ===",
            f"总任务数: {result.total_tasks}",
            f"通过数: {result.passed_tasks}",
            f"成功率: {result.success_rate*100:.1f}%",
            "",
            "=== Pass@K ===",
            f"Pass@1: {result.pass_at_1*100:.1f}%",
            f"Pass@3: {result.pass_at_3*100:.1f}%",
            f"Pass@{result.pass_at_k}: {result.pass_at_k*100:.1f}%",
            "",
            "=== 性能指标 ===",
            f"平均延迟: {result.avg_latency_ms:.1f}ms",
            f"平均 Token: {result.avg_tokens}",
        ]
        return "\n".join(lines)
    
    def generate_json(self, result: BenchmarkResult) -> Dict[str, Any]:
        """Generate JSON report"""
        return result.to_dict()
    
    def generate_markdown(self, result: BenchmarkResult) -> str:
        """Generate Markdown report"""
        return f"""
# Benchmark Report: {result.benchmark_name}

**执行时间**: {result.executed_at}

## 结果摘要

| 指标 | 值 |
|------|-----|
| 总任务数 | {result.total_tasks} |
| 通过数 | {result.passed_tasks} |
| 成功率 | {result.success_rate*100:.1f}% |
| Pass@1 | {result.pass_at_1*100:.1f}% |
| Pass@3 | {result.pass_at_3*100:.1f}% |
| 平均延迟 | {result.avg_latency_ms:.1f}ms |
| 平均 Token | {result.avg_tokens} |

## 任务详情

{self._generate_task_table(result)}
"""
    
    def _generate_task_table(self, result: BenchmarkResult) -> str:
        """Generate task results table"""
        lines = ["| Task ID | 状态 | 延迟 | Token |", "|---------|------|------|-------|"]
        
        for task in result.task_results[:20]:
            status = "✅" if task.success else "❌"
            lines.append(f"| {task.task_id} | {status} | {task.latency_ms}ms | {task.tokens_used} |")
        
        if len(result.task_results) > 20:
            lines.append(f"\n... 还有 {len(result.task_results) - 20} 个任务")
        
        return "\n".join(lines)
    
    def generate_regression_text(self, result: RegressionResult) -> str:
        """Generate regression text report"""
        status = "⚠️ 检测到回归" if result.has_regression else "✅ 无回归"
        
        lines = [
            f"回归检测结果: {status}",
            "",
            "=== 变化详情 ==="
        ]
        
        for metric, data in result.changes.items():
            lines.append(f"\n{metric}:")
            lines.append(f"  当前: {data.get('current', 'N/A')}")
            lines.append(f"  基线: {data.get('baseline', 'N/A')}")
            change = data.get('change', 0)
            lines.append(f"  变化: {change*100:+.1f}%")
        
        if result.recommendations:
            lines.append("\n=== 建议 ===")
            for rec in result.recommendations:
                lines.append(f"- {rec}")
        
        return "\n".join(lines)
    
    def save_report(self, result: BenchmarkResult, path: str, format: str = "text"):
        """Save report to file"""
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        if format == "json":
            content = self.generate_json(result)
            with open(path, "w") as f:
                import json
                json.dump(content, f, indent=2)
        elif format == "markdown":
            content = self.generate_markdown(result)
            with open(path, "w") as f:
                f.write(content)
        else:
            content = self.generate_text(result)
            with open(path, "w") as f:
                f.write(content)


def generate_report(result: BenchmarkResult, format: str = "text") -> str:
    """Generate report in specified format"""
    reporter = ResultReporter()
    
    if format == "json":
        return str(reporter.generate_json(result))
    elif format == "markdown":
        return reporter.generate_markdown(result)
    else:
        return reporter.generate_text(result)


__all__ = ["ResultReporter", "generate_report"]