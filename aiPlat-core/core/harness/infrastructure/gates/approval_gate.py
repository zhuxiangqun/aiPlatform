"""
ApprovalGate — dangerous command detection and approval enforcement.

Catalogue of dangerous operations with config-driven approval rules.
Integrated into PolicyGate.check_tool() as pre-check before execution.

hermes-agent parity: tools/approval.py — dangerous command catalog + approval flow
"""
from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class ApprovalVerdict(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    SAMPLED = "sampled"


class ApprovalSeverity(Enum):
    """Severity level of the dangerous operation."""
    CRITICAL = "critical"       # Data loss / security breach — always require approval
    HIGH = "high"               # Potential damage — require supervisor approval
    MEDIUM = "medium"           # Requires confirmation but auto-allowable in session
    LOW = "low"                 # Informational — logged but not blocked


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class ApprovalRule:
    """A single approval rule matching tool+args patterns."""
    rule_id: str
    tool_name: str
    arg_patterns: Dict[str, str] = field(default_factory=dict)
    severity: ApprovalSeverity = ApprovalSeverity.HIGH
    message: str = ""
    allow_if_session_approved: bool = False
    allow_if_user_whitelisted: bool = False
    sampling_rate: float = 1.0


@dataclass
class ApprovalGateResult:
    verdict: ApprovalVerdict
    rule_id: Optional[str] = None
    severity: Optional[ApprovalSeverity] = None
    message: str = ""
    require_interactive: bool = False
    approval_token: str = ""


# ── Dangerous Command Catalogue ──────────────────────────────────────────────

# Patterns that when matched in tool args trigger approval:
# Format: (tool_name_pattern, arg_key, arg_value_regex, severity, message)
_DANGEROUS_PATTERNS: List[Tuple[str, str, str, ApprovalSeverity, str]] = [
    # ── File System — data loss ──
    ("file_operations", "operation", r"^delete$", ApprovalSeverity.CRITICAL,
     "File deletion detected — this cannot be undone."),
    ("file_operations", "operation", r"^delete_recursive$", ApprovalSeverity.CRITICAL,
     "Recursive directory deletion detected — this cannot be undone."),
    ("file_operations", "path", r"(~|/home|/etc|/var|/usr|/bin|/sbin)", ApprovalSeverity.HIGH,
     "Operating on system directory — potential system impact."),
    ("file_operations", "path", r"\.(env|secret|key|pem|crt|passwd|shadow)\b", ApprovalSeverity.CRITICAL,
     "Operating on credential/sensitive file — potential secrets exposure."),

    # ── Shell / Code execution ──
    ("code_execution", "*", r".*", ApprovalSeverity.HIGH,
     "Arbitrary code execution requested."),
    ("shell_exec", "*", r".*", ApprovalSeverity.CRITICAL,
     "Shell command execution — possible system compromise."),
    ("code_execution", "*", r"\b(rm\s+-rf|sudo|chmod\s+777|wget\s+-O|curl\s+.*\|\s*bash|mkfs|dd\s+if=)\b",
     ApprovalSeverity.CRITICAL, "Potentially destructive command detected."),

    # ── Database — data integrity ──
    ("database", "operation", r"^drop_table$", ApprovalSeverity.CRITICAL,
     "Table drop detected — data will be lost."),
    ("database", "operation", r"^truncate$", ApprovalSeverity.CRITICAL,
     "Table truncation detected — data will be lost."),
    ("database", "operation", r"^alter_table$", ApprovalSeverity.HIGH,
     "Schema alteration — may break applications."),
    ("database", "operation", r"^drop_database$", ApprovalSeverity.CRITICAL,
     "Database drop detected — all data in database will be lost."),

    # ── Network — security boundary ──
    ("http", "url", r"^(?!https://)", ApprovalSeverity.MEDIUM,
     "Non-HTTPS URL — data in transit may be intercepted."),
    ("http", "method", r"^(DELETE|PATCH)$", ApprovalSeverity.MEDIUM,
     "Destructive HTTP method on external resource."),
    ("browser", "action", r"^(click|submit)$", ApprovalSeverity.LOW,
     "Browser interaction — verify target element."),

    # ── Auth / Permission changes ──
    ("permission_*", "*", r".*", ApprovalSeverity.CRITICAL,
     "Permission/role modification detected."),
    ("sysgraph_tools", "operation", r"^(revoke|grant).*", ApprovalSeverity.CRITICAL,
     "System permission change detected."),

    # ── Repository — destructive git operations ──
    ("repo", "operation", r"^(force_push|hard_reset|rebase|squash)$", ApprovalSeverity.CRITICAL,
     "Destructive git operation — history may be lost."),
    ("repo", "operation", r"^(branch_delete|tag_delete)$", ApprovalSeverity.HIGH,
     "Git ref deletion — branch/tag will be removed."),

    # ── Process management ──
    ("process", "operation", r"^(kill|terminate|stop)$", ApprovalSeverity.HIGH,
     "Process termination — service may be interrupted."),
    ("process", "operation", r"^(kill_9|force_kill)$", ApprovalSeverity.CRITICAL,
     "Force kill (SIGKILL) — process cannot gracefully shut down."),

    # ── Configuration changes ──
    ("skill_*", "operation", r"^(uninstall|delete|overwrite)$", ApprovalSeverity.HIGH,
     "Skill modification — may affect agent behavior."),
    ("agent_*", "operation", r"^(delete|disable|reset)$", ApprovalSeverity.HIGH,
     "Agent modification — may affect pipeline execution."),

    # ── Large-scale operations ──
    ("*", "batch_size", None, ApprovalSeverity.MEDIUM,
     "Batch operation — verify scope."),
    ("*", "max_files", None, ApprovalSeverity.LOW,
     "Multi-file operation — verify target scope."),
]


# Arg value threshold triggers (for numeric params):
_ARG_THRESHOLDS: List[Tuple[str, str, float, ApprovalSeverity, str]] = [
    ("file_operations", "batch_size", 100, ApprovalSeverity.MEDIUM,
     "Large batch file operation (>100 files)."),
    ("http", "concurrency", 10, ApprovalSeverity.MEDIUM,
     "High concurrency HTTP requests (>10 parallel)."),
    ("database", "batch_size", 1000, ApprovalSeverity.MEDIUM,
     "Large database batch operation (>1000 rows)."),
]


# ── Approval Gate ────────────────────────────────────────────────────────────

class ApprovalGate:
    """
    Pre-execution gate that checks tool calls against a dangerous-command catalogue.

    Integration point: called by PolicyGate.check_tool() before the permission check.
    If an approval is required, PolicyGate routes to the interactive approval flow.

    Usage:
        gate = ApprovalGate()
        result = gate.check("file_operations", {"operation": "delete", "path": "/tmp/test"})
        if result.verdict == ApprovalVerdict.ASK:
            # route to interactive approval
            ...
    """

    def __init__(self):
        self._rules: List[ApprovalRule] = []
        self._user_whitelist: Set[str] = set()
        self._session_approved: Dict[str, Set[str]] = {}  # session_id -> {rule_id, ...}
        self._approval_cache: Dict[str, Tuple[float, ApprovalVerdict]] = {}  # token -> (ts, verdict)
        self._cache_ttl: float = float(os.getenv("AIPLAT_APPROVAL_CACHE_TTL", "300"))  # 5 min

        # Override: fully disable approval gate
        self._disabled: bool = os.getenv("AIPLAT_APPROVAL_GATE_DISABLED", "false").lower() in ("1", "true", "yes")

        self._build_rules()

    def _build_rules(self):
        """Build internal rule list from catalogue + env overrides."""
        for idx, (tool_pat, arg_key, arg_regex, severity, message) in enumerate(_DANGEROUS_PATTERNS):
            self._rules.append(ApprovalRule(
                rule_id=f"danger_{idx:03d}",
                tool_name=tool_pat,
                arg_patterns={arg_key: arg_regex},
                severity=severity,
                message=message,
                allow_if_session_approved=(severity in (ApprovalSeverity.LOW, ApprovalSeverity.MEDIUM)),
                allow_if_user_whitelisted=(severity == ApprovalSeverity.LOW),
            ))

        # Load user whitelist from env
        whitelist = os.getenv("AIPLAT_APPROVAL_WHITELIST_USERS", "")
        for uid in whitelist.split(","):
            uid = uid.strip()
            if uid:
                self._user_whitelist.add(uid)

    def check(self, tool_name: str, tool_args: dict, user_id: str = "", session_id: str = "") -> ApprovalGateResult:
        """
        Check if a tool call requires approval.

        Returns ApprovalGateResult with verdict and reason.
        """
        if self._disabled:
            return ApprovalGateResult(verdict=ApprovalVerdict.ALLOW)

        # Step 1: rules sorted by specificity (non-wildcard args first, then severity)
        rules_sorted = sorted(self._rules, key=lambda r: (
            0 if all(k != "*" and v is not None for k, v in r.arg_patterns.items()) else 1,
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r.severity.value, 99),
        ))
        for rule in rules_sorted:
            if not fnmatch.fnmatch(tool_name, rule.tool_name):
                continue

            # Check arg patterns
            matched = False
            for arg_key, arg_pattern in rule.arg_patterns.items():
                if arg_key == "*":
                    for val in tool_args.values():
                        if arg_pattern is None or re.search(arg_pattern, str(val)):
                            matched = True
                            break
                elif arg_pattern is None:
                    if arg_key in tool_args:
                        matched = True
                        break
                else:
                    arg_val = str(tool_args.get(arg_key, ""))
                    if re.search(arg_pattern, arg_val):
                        matched = True
                        break

            # Check numeric thresholds (only when arg_key was assigned)
            if not matched and rule.arg_patterns:
                first_key = next(iter(rule.arg_patterns), "")
                if first_key == "batch_size":
                    batch_val = tool_args.get("batch_size", 0)
                    if isinstance(batch_val, (int, float)) and batch_val > 100:
                        matched = True
                    elif isinstance(batch_val, str) and batch_val.isdigit() and int(batch_val) > 100:
                        matched = True

            if not matched and rule.arg_patterns:
                continue

            # Rule matched — determine verdict
            if rule.severity == ApprovalSeverity.CRITICAL:
                return ApprovalGateResult(
                    verdict=ApprovalVerdict.ASK,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    message=rule.message,
                    require_interactive=True,
                )

            if rule.severity == ApprovalSeverity.HIGH:
                # Check session cache
                if rule.allow_if_session_approved and session_id:
                    session_rules = self._session_approved.get(session_id, set())
                    if rule.rule_id in session_rules:
                        return ApprovalGateResult(verdict=ApprovalVerdict.ALLOW)

                return ApprovalGateResult(
                    verdict=ApprovalVerdict.ASK,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    message=rule.message,
                    require_interactive=True,
                )

            if rule.severity == ApprovalSeverity.MEDIUM:
                if rule.allow_if_session_approved and session_id:
                    session_rules = self._session_approved.get(session_id, set())
                    if rule.rule_id in session_rules:
                        return ApprovalGateResult(verdict=ApprovalVerdict.ALLOW)

                return ApprovalGateResult(
                    verdict=ApprovalVerdict.ASK,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    message=rule.message,
                    require_interactive=False,  # auto-allowable
                )

            if rule.severity == ApprovalSeverity.LOW:
                if rule.allow_if_user_whitelisted and user_id in self._user_whitelist:
                    return ApprovalGateResult(verdict=ApprovalVerdict.ALLOW)
                return ApprovalGateResult(
                    verdict=ApprovalVerdict.ALLOW,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    message=rule.message,
                )

        return ApprovalGateResult(verdict=ApprovalVerdict.ALLOW)

    def approve_session_rule(self, session_id: str, rule_id: str):
        """Record that a rule was approved for the duration of this session."""
        if session_id not in self._session_approved:
            self._session_approved[session_id] = set()
        self._session_approved[session_id].add(rule_id)

    def revoke_session_approval(self, session_id: str, rule_id: Optional[str] = None):
        """Revoke session-level approval for one or all rules."""
        if rule_id is None:
            self._session_approved.pop(session_id, None)
        elif session_id in self._session_approved:
            self._session_approved[session_id].discard(rule_id)

    def add_rule(self, rule: ApprovalRule):
        """Programmatically add a custom approval rule."""
        self._rules.append(rule)

    def remove_rule(self, rule_id: str):
        """Remove a rule by rule_id."""
        self._rules = [r for r in self._rules if r.rule_id != rule_id]

    def list_rules(self) -> List[Dict[str, Any]]:
        """Return all active rules (for UI display)."""
        return [
            {
                "rule_id": r.rule_id,
                "tool_name": r.tool_name,
                "severity": r.severity.value,
                "message": r.message,
            }
            for r in self._rules
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Return current gate statistics."""
        return {
            "total_rules": len(self._rules),
            "whitelisted_users": len(self._user_whitelist),
            "active_sessions": len(self._session_approved),
            "disabled": self._disabled,
            "cache_size": len(self._approval_cache),
        }


# ── Global Singleton ──────────────────────────────────────────────────────────

_approval_gate: Optional[ApprovalGate] = None


def get_approval_gate() -> ApprovalGate:
    """Get or create the global ApprovalGate singleton."""
    global _approval_gate
    if _approval_gate is None:
        _approval_gate = ApprovalGate()
    return _approval_gate


def reset_approval_gate():
    """Reset the global singleton (for testing)."""
    global _approval_gate
    _approval_gate = None
