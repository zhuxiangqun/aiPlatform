"""
Security Scanner

Scans content for sensitive information and security vulnerabilities.
"""

import re
from typing import Any, Dict, List, Pattern
from datetime import datetime
from dataclasses import field

from .types import (
    Vulnerability,
    VulnerabilitySeverity,
    VulnerabilityType,
    SecurityScanResult,
)


class SecurityScanner:
    """Security Scanner - Detects sensitive info and vulnerabilities"""

    PATTERNS: Dict[VulnerabilityType, List[Pattern]] = {
        VulnerabilityType.API_KEY: [
            re.compile(r'sk-[a-zA-Z0-9]{20,}', re.IGNORECASE),
            re.compile(r'api[_-]?key["\s:=]+[a-zA-Z0-9]{20,}', re.IGNORECASE),
            re.compile(r'openai[_-]?api[_-]?key["\s:=]+[a-zA-Z0-9]{20,}', re.IGNORECASE),
            re.compile(r'anthropic[_-]?api[_-]?key["\s:=]+[a-zA-Z0-9]{20,}', re.IGNORECASE),
        ],
        VulnerabilityType.CREDENTIALS: [
            re.compile(r'AKIA[0-9A-Z]{16}', re.IGNORECASE),
            re.compile(r'aws[_-]?access[_-]?key[_-]?id["\s:=]+[A-Z0-9]{20}', re.IGNORECASE),
            re.compile(r'ghp_[a-zA-Z0-9]{36,}', re.IGNORECASE),
            re.compile(r'github[_-]?token["\s:=]+[a-zA-Z0-9]{36,}', re.IGNORECASE),
            re.compile(r'password["\s:=]+\S+', re.IGNORECASE),
            re.compile(r'secret[_-]?key["\s:=]+\S+', re.IGNORECASE),
        ],
        VulnerabilityType.PATH_TRAVERSAL: [
            re.compile(r'\.\.[/\\]', re.IGNORECASE),
            re.compile(r'/etc/passwd', re.IGNORECASE),
            re.compile(r'C:\\Windows\\System32', re.IGNORECASE),
        ],
        VulnerabilityType.SQL_INJECTION: [
            re.compile(r"(['\"];\s*(?:drop|delete|insert|update|create)\s)", re.IGNORECASE),
            re.compile(r"(union\s+select)", re.IGNORECASE),
            re.compile(r"(\bor\b\s+\d+\s*=\s*\d+)", re.IGNORECASE),
            re.compile(r"(--\s*$)", re.IGNORECASE),
        ],
        VulnerabilityType.COMMAND_INJECTION: [
            re.compile(r'[;&|`$]\s*(?:cat|ls|rm|wget|curl|sh|bash|cmd)\b', re.IGNORECASE),
            re.compile(r'\$\([^)]+\)', re.IGNORECASE),
            re.compile(r'`[^`]+`', re.IGNORECASE),
        ],
        VulnerabilityType.SECRET: [
            re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', re.IGNORECASE),
            re.compile(r'token["\s:=]+[a-zA-Z0-9_-]{20,}', re.IGNORECASE),
            re.compile(r'bearer\s+[a-zA-Z0-9_-]{20,}', re.IGNORECASE),
        ],
        VulnerabilityType.PII: [
            re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'),  # SSN
            re.compile(r'\b\d{16}\b'),  # Credit card
            re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),  # Email
        ],
    }

    SEVERITY_MAP = {
        VulnerabilityType.API_KEY: VulnerabilitySeverity.HIGH,
        VulnerabilityType.CREDENTIALS: VulnerabilitySeverity.CRITICAL,
        VulnerabilityType.PATH_TRAVERSAL: VulnerabilitySeverity.HIGH,
        VulnerabilityType.SQL_INJECTION: VulnerabilitySeverity.CRITICAL,
        VulnerabilityType.COMMAND_INJECTION: VulnerabilitySeverity.CRITICAL,
        VulnerabilityType.SECRET: VulnerabilitySeverity.HIGH,
        VulnerabilityType.PII: VulnerabilitySeverity.MEDIUM,
    }

    SUGGESTIONS = {
        VulnerabilityType.API_KEY: "Move API keys to environment variables or secrets manager",
        VulnerabilityType.CREDENTIALS: "Remove hardcoded credentials, use secure secret management",
        VulnerabilityType.PATH_TRAVERSAL: "Validate and sanitize file paths, use allowlist",
        VulnerabilityType.SQL_INJECTION: "Use parameterized queries or ORM, validate input",
        VulnerabilityType.COMMAND_INJECTION: "Avoid shell execution, use subprocess with args",
        VulnerabilityType.SECRET: "Store secrets in secure vault, never commit to version control",
        VulnerabilityType.PII: "Remove or mask PII, implement data protection policies",
    }

    def __init__(
        self,
        enabled_types: List[VulnerabilityType] = None,
        severity_threshold: VulnerabilitySeverity = VulnerabilitySeverity.MEDIUM
    ):
        self._enabled_types = enabled_types or list(VulnerabilityType)
        self._severity_threshold = severity_threshold

    async def scan(self, content: str, context: Dict[str, Any] = None) -> SecurityScanResult:
        """Execute security scan"""
        vulnerabilities: List[Vulnerability] = []
        context = context or {}

        for vuln_type in self._enabled_types:
            patterns = self.PATTERNS.get(vuln_type, [])
            
            for pattern in patterns:
                for match in pattern.finditer(content):
                    line_number = content[:match.start()].count('\n') + 1
                    snippet = self._get_snippet(content, line_number)

                    severity = self.SEVERITY_MAP.get(vuln_type, VulnerabilitySeverity.MEDIUM)
                    
                    if severity.value >= self._severity_threshold.value:
                        vulnerabilities.append(Vulnerability(
                            severity=severity,
                            type=vuln_type,
                            location=context.get("file", "unknown"),
                            description=f"Found potential {vuln_type.value}",
                            suggestion=self.SUGGESTIONS.get(vuln_type, "Review and fix"),
                            line_number=line_number,
                            snippet=snippet
                        ))

        vulnerabilities = self._deduplicate(vulnerabilities)

        return SecurityScanResult(
            passed=len([v for v in vulnerabilities if v.severity.value >= VulnerabilitySeverity.HIGH.value]) == 0,
            vulnerabilities=vulnerabilities,
            scanned_at=datetime.utcnow().isoformat(),
            scanned_content_length=len(content)
        )

    def _get_snippet(self, content: str, line_number: int, context_lines: int = 2) -> str:
        """Get code snippet around the line"""
        lines = content.split('\n')
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)
        
        snippet_lines = lines[start:end]
        return '\n'.join(f"{i+1}: {line}" for i, line in enumerate(snippet_lines, start=start))

    def _deduplicate(self, vulnerabilities: List[Vulnerability]) -> List[Vulnerability]:
        """Remove duplicate vulnerabilities"""
        seen = set()
        unique = []
        
        for v in vulnerabilities:
            key = (v.type, v.line_number)
            if key not in seen:
                seen.add(key)
                unique.append(v)
                
        return unique


def create_security_scanner(
    enabled_types: List[VulnerabilityType] = None,
    severity_threshold: VulnerabilitySeverity = VulnerabilitySeverity.MEDIUM
) -> SecurityScanner:
    """Create a security scanner instance"""
    return SecurityScanner(enabled_types=enabled_types, severity_threshold=severity_threshold)


__all__ = [
    "SecurityScanner",
    "create_security_scanner",
]