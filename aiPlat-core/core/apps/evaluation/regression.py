"""
Regression Detection Module

Detects performance regressions by comparing current results to baseline.
"""

from .types import BenchmarkResult, RegressionResult


class RegressionDetector:
    """Detects performance regressions"""
    
    def __init__(
        self,
        pass_rate_threshold: float = 0.05,
        token_increase_threshold: float = 0.20,
        latency_increase_threshold: float = 0.20
    ):
        self.pass_rate_threshold = pass_rate_threshold
        self.token_increase_threshold = token_increase_threshold
        self.latency_increase_threshold = latency_increase_threshold
    
    def detect(
        self,
        current: BenchmarkResult,
        baseline: BenchmarkResult
    ) -> RegressionResult:
        """Detect regression between current and baseline"""
        has_regression = False
        changes = {}
        recommendations = []
        
        pass_rate_change = current.pass_at_1 - baseline.pass_at_1
        if pass_rate_change < -self.pass_rate_threshold:
            has_regression = True
            changes["pass_rate"] = {
                "current": current.pass_at_1,
                "baseline": baseline.pass_at_1,
                "change": pass_rate_change
            }
            recommendations.append(
                f"成功率下降 {abs(pass_rate_change)*100:.1f}%，需要调查原因"
            )
        
        if baseline.avg_tokens > 0:
            token_change = (current.avg_tokens - baseline.avg_tokens) / baseline.avg_tokens
            if token_change > self.token_increase_threshold:
                has_regression = True
                changes["tokens"] = {
                    "current": current.avg_tokens,
                    "baseline": baseline.avg_tokens,
                    "change": token_change
                }
                recommendations.append(
                    f"Token 消耗增加 {token_change*100:.1f}%，考虑优化"
                )
        
        if baseline.avg_latency_ms > 0:
            latency_change = (current.avg_latency_ms - baseline.avg_latency_ms) / baseline.avg_latency_ms
            if latency_change > self.latency_increase_threshold:
                has_regression = True
                changes["latency"] = {
                    "current": current.avg_latency_ms,
                    "baseline": baseline.avg_latency_ms,
                    "change": latency_change
                }
                recommendations.append(
                    f"延迟增加 {latency_change*100:.1f}%，需要优化"
                )
        
        return RegressionResult(
            has_regression=has_regression,
            current_result=current,
            baseline_result=baseline,
            changes=changes,
            recommendations=recommendations
        )


async def check_regression(
    current: BenchmarkResult,
    baseline_path: str
) -> RegressionResult:
    """Check for regression against saved baseline"""
    import json
    
    try:
        with open(baseline_path, "r") as f:
            baseline_data = json.load(f)
        
        baseline = BenchmarkResult(
            benchmark_name=baseline_data.get("benchmark_name", ""),
            total_tasks=baseline_data.get("total_tasks", 0),
            passed_tasks=baseline_data.get("passed_tasks", 0),
            pass_at_1=baseline_data.get("pass_at_1", 0),
            pass_at_3=baseline_data.get("pass_at_3", 0),
            pass_at_k=baseline_data.get("pass_at_k", 0),
            avg_latency_ms=baseline_data.get("avg_latency_ms", 0),
            avg_tokens=baseline_data.get("avg_tokens", 0)
        )
        
        detector = RegressionDetector()
        return detector.detect(current, baseline)
        
    except FileNotFoundError:
        return RegressionResult(
            has_regression=False,
            current_result=current,
            baseline_result=current,
            changes={},
            recommendations=["未找到基线数据"]
        )


__all__ = ["RegressionDetector", "check_regression"]