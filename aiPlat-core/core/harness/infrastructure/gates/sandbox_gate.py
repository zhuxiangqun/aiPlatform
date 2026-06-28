"""
SandboxGate — pre-execution validation gate.

Inspired by ROSClaw's sandbox/firewall: validates parameters BEFORE execution,
not during. Checks filesystem safety, rate limits, resource budget, and
performs light pre-flight validation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

log = logging.getLogger(__name__)


class Verdict(str, Enum):
    PASS = "pass"
    REJECT = "reject"
    WARN = "warn"


@dataclass
class SandboxResult:
    verdict: Verdict
    reason: str = ""
    checks_passed: int = 0
    checks_total: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    duration_us: int = 0


class SandboxGate:
    """
    Pre-execution sandbox. Run before PolicyGate to catch obvious issues
    BEFORE context/token budget is consumed.
    
    Checks run in check():
      1. Filesystem safety — target paths within allowed workspace (path-traversal safe)
      2. Network safety — destination host in AIPLAT_NETWORK_WHITELIST (opt-in)
      3. Rate limits — not exceeding per-minute quotas
      4. Pattern safety — known-dangerous input patterns
    Planned but not yet enforced in check(): resource budget (token/time).
    """

    # Filesystem safety — paths that must NOT be written to
    _FORBIDDEN_PATHS: Tuple[str, ...] = (
        '/etc/', '/boot/', '/proc/', '/sys/', '/dev/',
        '~/.ssh/', '~/.aws/', '~/.gcloud/',
        '.git/config', '.env',
    )

    # Filesystem safety — allowed workspace prefixes
    _ALLOWED_PREFIXES: Tuple[str, ...] = (
        '/tmp/', '/var/tmp/',
    )

    # Rate limits per operation type (calls per minute)
    _RATE_LIMITS: Dict[str, int] = {
        "tool:bash": 10,
        "tool:shell": 10,
        "tool:run_command": 10,
        "tool:file_write": 60,
        "tool:file_delete": 20,
        "tool:network": 30,
    }

    # Rate tracking (in-memory, reset on restart)
    _rate_counters: Dict[str, List[float]] = {}
    _rate_window: float = 60.0  # seconds

    # Resource budgets
    _MAX_TOKENS_PER_TOOL: int = 100_000
    _MAX_TIMEOUT_PER_TOOL: float = 300.0

    # Dangerous patterns for file operations
    _DANGEROUS_PATTERNS: Tuple[re.Pattern, ...] = (
        re.compile(r'rm\s+-rf\s+/'),
        re.compile(r'>\s*/dev/sda'),
        re.compile(r'mkfs\.'),
        re.compile(r'dd\s+if='),
        re.compile(r'chmod\s+777\s+/'),
    )

    async def check(
        self,
        *,
        kind: str = "tool",
        tool_name: str = "",
        tool_args: Dict[str, Any] = None,
        file_path: str = "",
    ) -> SandboxResult:
        """
        Run all safety checks. Returns PASS/REJECT/WARN with details.
        """
        tool_args = tool_args or {}
        checks: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = [
            ("filesystem", lambda: self._check_filesystem(file_path)),
            ("network", lambda: self._check_network(tool_args)),
            ("rate_limit", lambda: self._check_rate_limit(tool_name)),
            ("pattern", lambda: self._check_patterns(tool_args)),
        ]

        start = time.monotonic()
        passed = 0
        warnings: List[str] = []
        rejections: List[str] = []
        details: Dict[str, Any] = {}

        for check_name, check_fn in checks:
            ok, msg = check_fn()
            details[check_name] = msg
            if ok:
                passed += 1
            elif msg.startswith("WARN:"):
                warnings.append(msg)
            else:
                rejections.append(msg)

        elapsed_us = int((time.monotonic() - start) * 1_000_000)

        if rejections:
            return SandboxResult(
                verdict=Verdict.REJECT,
                reason="; ".join(rejections),
                checks_passed=passed,
                checks_total=len(checks),
                details=details,
                duration_us=elapsed_us,
            )
        elif warnings:
            return SandboxResult(
                verdict=Verdict.WARN,
                reason="; ".join(warnings),
                checks_passed=passed,
                checks_total=len(checks),
                details=details,
                duration_us=elapsed_us,
            )
        else:
            return SandboxResult(
                verdict=Verdict.PASS,
                reason="All checks passed",
                checks_passed=passed,
                checks_total=len(checks),
                details=details,
                duration_us=elapsed_us,
            )

    def _check_filesystem(self, path: str) -> Tuple[bool, str]:
        """Check if target path is safe for read/write operations."""
        if not path:
            return (True, "no filesystem operation")

        # Normalize to resolve '..' traversal (lexical — works for not-yet-created paths).
        # Without this, '<ws>/../../etc/passwd' literally starts with the workspace prefix
        # and bypasses both the forbidden-path and workspace checks (sandbox escape).
        expanded = os.path.normpath(os.path.expanduser(path))

        def _under(base: str) -> bool:
            base = os.path.normpath(os.path.expanduser(base))
            # Boundary-aware so a sibling like '<base>EVIL' does not match '<base>'.
            return expanded == base or expanded.startswith(base.rstrip(os.sep) + os.sep)

        # Forbidden paths
        for forbidden in self._FORBIDDEN_PATHS:
            if _under(forbidden):
                return (False, f"REJECT: path '{path}' matches forbidden pattern '{forbidden}'")

        # Must be within workspace or an allowed prefix (boundary-aware)
        workspace = os.environ.get("AIPLAT_WORKSPACE_ROOT", os.path.expanduser("~/.aiplat"))
        if _under(workspace):
            return (True, f"path in workspace: {expanded}")

        for allowed in self._ALLOWED_PREFIXES:
            if _under(allowed):
                return (True, f"path in allowed prefix: {expanded}")

        return (False, f"REJECT: path '{path}' not in allowed workspace")

    def _check_rate_limit(self, tool_name: str) -> Tuple[bool, str]:
        """Check if operation exceeds per-minute rate limit."""
        if not tool_name:
            return (True, "no rate limit check needed")

        limit = self._RATE_LIMITS.get(tool_name, 60)  # default 60/min
        now = time.time()

        if tool_name not in self._rate_counters:
            self._rate_counters[tool_name] = []

        # Prune old entries
        cutoff = now - self._rate_window
        self._rate_counters[tool_name] = [t for t in self._rate_counters[tool_name] if t > cutoff]

        count = len(self._rate_counters[tool_name])

        if count >= limit:
            return (False, f"REJECT: {tool_name} rate limit exceeded ({count}/{limit} per {self._rate_window}s)")

        if count >= limit * 0.8:
            self._rate_counters[tool_name].append(now)
            return (True, f"WARN: {tool_name} approaching rate limit ({count}/{limit})")

        self._rate_counters[tool_name].append(now)
        return (True, f"rate OK ({count + 1}/{limit})")

    def _check_patterns(self, args: Dict[str, Any]) -> Tuple[bool, str]:
        """Check for known-dangerous patterns in arguments."""
        for key, value in args.items():
            if isinstance(value, str):
                for pattern in self._DANGEROUS_PATTERNS:
                    if pattern.search(value):
                        return (False, f"REJECT: dangerous pattern '{pattern.pattern}' in arg '{key}'")
        return (True, "no dangerous patterns detected")

    def _check_network(self, args: Dict[str, Any]) -> Tuple[bool, str]:
        """Check network destination against an optional whitelist.

        Opt-in: enforced only when AIPLAT_NETWORK_WHITELIST is configured
        (comma-separated hosts/domains; subdomains allowed). Empty whitelist
        means no enforcement (backward compatible). Restricts network tools to
        allowed hosts to prevent exfiltration to arbitrary destinations.
        """
        whitelist_raw = os.getenv("AIPLAT_NETWORK_WHITELIST", "").strip()
        if not whitelist_raw:
            return (True, "no network whitelist configured")
        dest = ""
        for k in ("url", "endpoint", "host", "uri", "target_url"):
            v = (args or {}).get(k)
            if isinstance(v, str) and v.strip():
                dest = v.strip()
                break
        if not dest:
            return (True, "no network destination")
        try:
            from urllib.parse import urlparse
            parsed = urlparse(dest if "://" in dest else "//" + dest)
            host = (parsed.hostname or "").lower()
        except Exception:
            host = dest.lower()
        if not host:
            return (True, "no host parsed")
        allowed = [w.strip().lower() for w in whitelist_raw.split(",") if w.strip()]
        for w in allowed:
            if host == w or host.endswith("." + w):
                return (True, f"host '{host}' in whitelist")
        return (False, f"REJECT: network destination '{host}' not in whitelist")


_sandbox_instance: Optional[SandboxGate] = None


def get_sandbox() -> SandboxGate:
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = SandboxGate()
    return _sandbox_instance


__all__ = ["SandboxGate", "SandboxResult", "Verdict", "get_sandbox"]
