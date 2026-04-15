"""
Quality Module

Provides quality gates, security scanning, and result verification.
"""

from .types import (
    CheckSeverity,
    CheckStatus,
    CheckResult,
    QualityGateResult,
    VulnerabilitySeverity,
    VulnerabilityType,
    Vulnerability,
    SecurityScanResult,
    VerificationType,
    VerificationSpec,
    VerificationResult,
)

from .gates import (
    QualityGate,
    ExecutionContext,
    create_quality_gate,
)

from .scanner import (
    SecurityScanner,
    create_security_scanner,
)

from .verifier import (
    ResultVerifier,
    create_verifier,
)


__all__ = [
    # Types
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
    # Gates
    "QualityGate",
    "ExecutionContext",
    "create_quality_gate",
    # Scanner
    "SecurityScanner",
    "create_security_scanner",
    # Verifier
    "ResultVerifier",
    "create_verifier",
]