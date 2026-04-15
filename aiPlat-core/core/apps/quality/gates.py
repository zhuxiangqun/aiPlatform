"""
Quality Gate

Automated quality checks for code and output validation.
"""

import ast
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .types import (
    CheckResult,
    CheckStatus,
    CheckSeverity,
    QualityGateResult,
)


class QualityGate:
    """Quality Gate - Automated quality checks"""

    DEFAULT_THRESHOLDS = {
        "max_complexity": 15,
        "max_lines": 1000,
        "error_rate": 0.05,
        "min_quality_score": 80,
    }

    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
        enabled_checks: Optional[List[str]] = None
    ):
        self._thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._enabled_checks = enabled_checks or [
            "syntax",
            "complexity",
            "error_rate",
            "quality_score"
        ]

    async def check(self, context: "ExecutionContext") -> QualityGateResult:
        """Execute quality gate checks"""
        checks: List[CheckResult] = []
        total_score = 100.0
        failed_count = 0

        # Syntax check
        if "syntax" in self._enabled_checks:
            result = await self._check_syntax(context)
            checks.append(result)
            if result.status == CheckStatus.FAILED:
                failed_count += 1
                total_score -= 25

        # Complexity check
        if "complexity" in self._enabled_checks:
            result = await self._check_complexity(context)
            checks.append(result)
            if result.status == CheckStatus.FAILED:
                failed_count += 1
                total_score -= 20

        # Error rate check
        if "error_rate" in self._enabled_checks:
            result = await self._check_error_rate(context)
            checks.append(result)
            if result.status == CheckStatus.FAILED:
                failed_count += 1
                total_score -= 25

        # Quality score check
        if "quality_score" in self._enabled_checks:
            result = await self._check_quality_score(context)
            checks.append(result)
            if result.status == CheckStatus.FAILED:
                failed_count += 1
                total_score -= 30

        passed = failed_count == 0
        score = max(0.0, total_score)

        suggestions = []
        for check in checks:
            if check.status == CheckStatus.FAILED:
                suggestions.extend(check.suggestions)

        return QualityGateResult(
            passed=passed,
            score=score,
            checks=checks,
            message=f"Quality gate {'passed' if passed else 'failed'}: {failed_count} check(s) failed",
            suggestions=suggestions[:5]
        )

    async def _check_syntax(self, context: "ExecutionContext") -> CheckResult:
        """Check code syntax"""
        code = context.get("code", "")
        language = context.get("language", "python")

        if not code:
            return CheckResult(
                name="syntax",
                status=CheckStatus.SKIPPED,
                message="No code provided"
            )

        if language == "python":
            try:
                ast.parse(code)
                return CheckResult(
                    name="syntax",
                    status=CheckStatus.PASSED,
                    message="Python syntax is valid"
                )
            except SyntaxError as e:
                return CheckResult(
                    name="syntax",
                    status=CheckStatus.FAILED,
                    severity=CheckSeverity.HIGH,
                    message=f"Syntax error: {e.msg} at line {e.lineno}",
                    suggestions=[f"Fix syntax error on line {e.lineno}"]
                )

        return CheckResult(
            name="syntax",
            status=CheckStatus.SKIPPED,
            message=f"Syntax check not supported for {language}"
        )

    async def _check_complexity(self, context: "ExecutionContext") -> CheckResult:
        """Check code complexity"""
        code = context.get("code", "")
        language = context.get("language", "python")
        max_complexity = self._thresholds.get("max_complexity", 15)

        if not code:
            return CheckResult(
                name="complexity",
                status=CheckStatus.SKIPPED,
                message="No code provided"
            )

        if language == "python":
            try:
                tree = ast.parse(code)
                complexity = self._calculate_complexity(tree)
                
                if complexity > max_complexity:
                    return CheckResult(
                        name="complexity",
                        status=CheckStatus.FAILED,
                        severity=CheckSeverity.MEDIUM,
                        message=f"Cyclomatic complexity {complexity} exceeds threshold {max_complexity}",
                        value=complexity,
                        threshold=max_complexity,
                        suggestions=["Refactor complex code into smaller functions", "Extract nested conditions"]
                    )
                
                return CheckResult(
                    name="complexity",
                    status=CheckStatus.PASSED,
                    message=f"Cyclomatic complexity {complexity} is within threshold",
                    value=complexity,
                    threshold=max_complexity
                )
            except SyntaxError:
                return CheckResult(
                    name="complexity",
                    status=CheckStatus.SKIPPED,
                    message="Cannot check complexity due to syntax errors"
                )

        return CheckResult(
            name="complexity",
            status=CheckStatus.SKIPPED,
            message=f"Complexity check not supported for {language}"
        )

    def _calculate_complexity(self, tree: ast.AST) -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
                
        return complexity

    async def _check_error_rate(self, context: "ExecutionContext") -> CheckResult:
        """Check error rate from feedback"""
        feedback = context.get("feedback", {})
        max_rate = self._thresholds.get("error_rate", 0.05)

        total = feedback.get("total", 0)
        errors = feedback.get("errors", 0)

        if total == 0:
            return CheckResult(
                name="error_rate",
                status=CheckStatus.PASSED,
                message="No feedback entries to check",
                value=0.0,
                threshold=max_rate
            )

        error_rate = errors / total

        if error_rate > max_rate:
            return CheckResult(
                name="error_rate",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.HIGH,
                message=f"Error rate {error_rate:.2%} exceeds threshold {max_rate:.2%}",
                value=error_rate,
                threshold=max_rate,
                suggestions=["Review and fix failed operations", "Add retry logic for failed operations"]
            )

        return CheckResult(
            name="error_rate",
            status=CheckStatus.PASSED,
            message=f"Error rate {error_rate:.2%} is within threshold",
            value=error_rate,
            threshold=max_rate
        )

    async def _check_quality_score(self, context: "ExecutionContext") -> CheckResult:
        """Check quality score"""
        score = context.get("quality_score", 100)
        min_score = self._thresholds.get("min_quality_score", 80)

        if score < min_score:
            return CheckResult(
                name="quality_score",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.MEDIUM,
                message=f"Quality score {score} below threshold {min_score}",
                value=score,
                threshold=min_score,
                suggestions=["Improve code quality", "Add more comprehensive comments", "Improve structure"]
            )

        return CheckResult(
            name="quality_score",
            status=CheckStatus.PASSED,
            message=f"Quality score {score} meets threshold",
            value=score,
            threshold=min_score
        )


@dataclass
class ExecutionContext:
    """Context for quality gate execution"""
    code: str = ""
    language: str = "python"
    feedback: Dict[str, Any] = field(default_factory=dict)
    quality_score: float = 100.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default) or default


def create_quality_gate(
    thresholds: Optional[Dict[str, float]] = None,
    enabled_checks: Optional[List[str]] = None
) -> QualityGate:
    """Create a quality gate instance"""
    return QualityGate(thresholds=thresholds, enabled_checks=enabled_checks)


__all__ = [
    "QualityGate",
    "ExecutionContext",
    "create_quality_gate",
]