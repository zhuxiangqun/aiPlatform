"""
Quality Module Types

Data structures for quality gates, security scanning, and verification.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class CheckSeverity(Enum):
    """Check severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CheckStatus(Enum):
    """Check status"""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class CheckResult:
    """Result of a single quality check"""
    name: str
    status: CheckStatus
    severity: CheckSeverity = CheckSeverity.LOW
    message: str = ""
    value: Any = None
    threshold: Any = None
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "suggestions": self.suggestions,
            "metadata": self.metadata
        }


@dataclass
class QualityGateResult:
    """Result of quality gate evaluation"""
    passed: bool
    score: float
    checks: List[CheckResult]
    message: str = ""
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "checks": [c.to_dict() for c in self.checks],
            "message": self.message,
            "suggestions": self.suggestions,
            "metadata": self.metadata
        }


class VulnerabilitySeverity(Enum):
    """Vulnerability severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VulnerabilityType(Enum):
    """Vulnerability types"""
    API_KEY = "api_key"
    CREDENTIALS = "credentials"
    PATH_TRAVERSAL = "path_traversal"
    SQL_INJECTION = "sql_injection"
    COMMAND_INJECTION = "command_injection"
    SECRET = "secret"
    PII = "pii"


@dataclass
class Vulnerability:
    """Security vulnerability"""
    severity: VulnerabilitySeverity
    type: VulnerabilityType
    location: str
    description: str
    suggestion: str
    line_number: Optional[int] = None
    snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "type": self.type.value,
            "location": self.location,
            "description": self.description,
            "suggestion": self.suggestion,
            "line_number": self.line_number,
            "snippet": self.snippet
        }


@dataclass
class SecurityScanResult:
    """Result of security scan"""
    passed: bool
    vulnerabilities: List[Vulnerability]
    scanned_at: str = ""
    scanned_content_length: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == VulnerabilitySeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == VulnerabilitySeverity.HIGH)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
            "scanned_at": self.scanned_at,
            "scanned_content_length": self.scanned_content_length,
            "critical_count": self.critical_count,
            "high_count": self.high_count
        }


class VerificationType(Enum):
    """Verification types"""
    ASSERTION = "assertion"
    SCHEMA = "schema"
    REGRESSION = "regression"
    THRESHOLD = "threshold"


@dataclass
class VerificationSpec:
    """Specification for result verification"""
    type: VerificationType
    spec: Dict[str, Any]
    threshold: Optional[float] = None


@dataclass
class VerificationResult:
    """Result of verification"""
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "message": self.message,
            "details": self.details
        }


__all__ = [
    "CheckSeverity",
    "CheckStatus",
    "CheckResult",
    "QualityGateResult",
    "VulnerabilitySeverity",
    "VulnerabilityType",
    "Vulnerability",
    "SecurityScanResult",
    "VerificationType",
    "VerificationSpec",
    "VerificationResult",
]