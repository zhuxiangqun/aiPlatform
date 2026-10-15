"""
ApprovalGate — dangerous command detection and approval enforcement.

Catalogue of dangerous operations with config-driven approval rules.
Integrated into PolicyGate.check_tool() as pre-check before execution.

hermes-agent parity: tools/approval.py — dangerous command catalog + approval flow

OpenWorker-inspired hard floors (2026-10): CRITICAL matches always escalate to a
human — auto-approve modes, session caches, and AIPLAT_APPROVALS_DISABLED cannot
lower them. Only ``AIPLAT_HARD_FLOOR_DISABLED=1`` (audited escape) skips floors.
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
    CRITICAL = "critical"       # Hard floor — always require interactive approval
    HIGH = "high"               # Potential damage — require supervisor approval
    MEDIUM = "medium"           # Requires confirmation but auto-allowable in session
    LOW = "low"                 # Informational — logged but not blocked


# Provenance sources written into audit detail["approval_provenance"].
APPROVAL_SOURCE_NONE = "none"
APPROVAL_SOURCE_HARD_FLOOR = "hard_floor"
APPROVAL_SOURCE_GATE_ASK = "gate_ask"
APPROVAL_SOURCE_GATE_DENY = "gate_deny"
APPROVAL_SOURCE_AUTO = "auto"
APPROVAL_SOURCE_HUMAN = "human"
APPROVAL_SOURCE_DISABLED = "approvals_disabled"


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
    hard_floor: bool = False  # True for CRITICAL — never auto-waived


@dataclass
class ApprovalGateResult:
    verdict: ApprovalVerdict
    rule_id: Optional[str] = None
    severity: Optional[ApprovalSeverity] = None
    message: str = ""
    require_interactive: bool = False
    approval_token: str = ""
    hard_floor: bool = False
    approval_source: str = APPROVAL_SOURCE_NONE


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

        # Override: soft-disable non-floor rules (hard floors still apply unless
        # AIPLAT_HARD_FLOOR_DISABLED=1).
        self._disabled: bool = os.getenv("AIPLAT_APPROVAL_GATE_DISABLED", "false").lower() in ("1", "true", "yes")
        self._hard_floor_disabled: bool = os.getenv("AIPLAT_HARD_FLOOR_DISABLED", "false").lower() in (
            "1", "true", "yes",
        )

        self._build_rules()

    def _build_rules(self):
        """Build internal rule list from catalogue + env overrides."""
        for idx, (tool_pat, arg_key, arg_regex, severity, message) in enumerate(_DANGEROUS_PATTERNS):
            is_floor = severity == ApprovalSeverity.CRITICAL
            self._rules.append(ApprovalRule(
                rule_id=f"danger_{idx:03d}",
                tool_name=tool_pat,
                arg_patterns={arg_key: arg_regex},
                severity=severity,
                message=message,
                # CRITICAL never session-auto; MEDIUM/LOW may graduate (HIGH stays interactive).
                allow_if_session_approved=(
                    severity in (ApprovalSeverity.LOW, ApprovalSeverity.MEDIUM)
                    and not is_floor
                ),
                allow_if_user_whitelisted=(severity == ApprovalSeverity.LOW),
                hard_floor=is_floor,
            ))

        # Load user whitelist from env
        whitelist = os.getenv("AIPLAT_APPROVAL_WHITELIST_USERS", "")
        for uid in whitelist.split(","):
            uid = uid.strip()
            if uid:
                self._user_whitelist.add(uid)

    def _match_rule(self, rule: ApprovalRule, tool_name: str, tool_args: dict) -> bool:
        if not fnmatch.fnmatch(tool_name, rule.tool_name):
            return False
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
        if not matched and rule.arg_patterns:
            first_key = next(iter(rule.arg_patterns), "")
            if first_key == "batch_size":
                batch_val = tool_args.get("batch_size", 0)
                if isinstance(batch_val, (int, float)) and batch_val > 100:
                    matched = True
                elif isinstance(batch_val, str) and batch_val.isdigit() and int(batch_val) > 100:
                    matched = True
        if not matched and rule.arg_patterns:
            return False
        return True

    def check_hard_floor(
        self,
        tool_name: str,
        tool_args: Optional[dict] = None,
        *,
        user_id: str = "",
        session_id: str = "",
    ) -> ApprovalGateResult:
        """Evaluate only hard-floor (CRITICAL) rules.

        Used when PolicyGate has approvals soft-disabled — floors still escalate.
        """
        if self._hard_floor_disabled:
            return ApprovalGateResult(
                verdict=ApprovalVerdict.ALLOW,
                approval_source=APPROVAL_SOURCE_DISABLED,
                message="hard floors disabled via AIPLAT_HARD_FLOOR_DISABLED",
            )
        args = tool_args or {}

        # OpenWorker P1: opaque constructs / arg-executors / dangerous flags escalate
        # even when the matching catalogue rule is only HIGH (e.g. code_execution).
        shell_floor = self._shell_hard_floor(tool_name, args)
        if shell_floor is not None:
            return shell_floor

        for rule in self._rules:
            if not rule.hard_floor and rule.severity != ApprovalSeverity.CRITICAL:
                continue
            if not self._match_rule(rule, tool_name, args):
                continue
            msg = rule.message
            # Enrich shell_exec blanket CRITICAL with specific command reasons.
            try:
                from core.harness.infrastructure.gates.shell_command_risk import (
                    evaluate_tool_shell_risk,
                )
                report = evaluate_tool_shell_risk(tool_name, args)
                if report and report.summary:
                    msg = f"{rule.message} [{report.summary}]"
            except Exception as e:
                logging.debug("shell risk enrich skipped: %s", e, exc_info=True)
            return ApprovalGateResult(
                verdict=ApprovalVerdict.ASK,
                rule_id=rule.rule_id,
                severity=ApprovalSeverity.CRITICAL,
                message=msg,
                require_interactive=True,
                hard_floor=True,
                approval_source=APPROVAL_SOURCE_HARD_FLOOR,
            )
        return ApprovalGateResult(verdict=ApprovalVerdict.ALLOW, approval_source=APPROVAL_SOURCE_NONE)

    def _shell_hard_floor(
        self, tool_name: str, tool_args: dict,
    ) -> Optional[ApprovalGateResult]:
        """Force CRITICAL when shell heuristics say so (prefix allowlists cannot waive)."""
        try:
            from core.harness.infrastructure.gates.shell_command_risk import (
                evaluate_tool_shell_risk,
            )
            report = evaluate_tool_shell_risk(tool_name, tool_args)
        except Exception as e:
            logging.debug("shell hard-floor check failed: %s", e, exc_info=True)
            return None
        if report is None or not report.forces_hard_floor:
            return None
        return ApprovalGateResult(
            verdict=ApprovalVerdict.ASK,
            rule_id="shell_risk_escalation",
            severity=ApprovalSeverity.CRITICAL,
            message=f"Shell command requires human approval — {report.summary}",
            require_interactive=True,
            hard_floor=True,
            approval_source=APPROVAL_SOURCE_HARD_FLOOR,
        )

    def check(
        self,
        tool_name: str,
        tool_args: dict,
        user_id: str = "",
        session_id: str = "",
        *,
        auto_approve: bool = False,
    ) -> ApprovalGateResult:
        """
        Check if a tool call requires approval.

        ``auto_approve=True`` may waive MEDIUM (and session-cached HIGH) but never
        CRITICAL hard floors. Soft-disable (``_disabled``) skips non-floor rules
        only; floors still ASK unless ``AIPLAT_HARD_FLOOR_DISABLED``.
        """
        args = tool_args or {}

        # Hard floors first — even when gate soft-disabled or auto_approve.
        floor = self.check_hard_floor(
            tool_name, args, user_id=user_id, session_id=session_id,
        )
        if floor.verdict == ApprovalVerdict.ASK:
            return floor

        if self._disabled:
            return ApprovalGateResult(
                verdict=ApprovalVerdict.ALLOW,
                approval_source=APPROVAL_SOURCE_DISABLED,
            )

        rules_sorted = sorted(self._rules, key=lambda r: (
            0 if all(k != "*" and v is not None for k, v in r.arg_patterns.items()) else 1,
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r.severity.value, 99),
        ))
        for rule in rules_sorted:
            if rule.hard_floor or rule.severity == ApprovalSeverity.CRITICAL:
                continue  # already handled
            if not self._match_rule(rule, tool_name, args):
                continue

            if rule.severity == ApprovalSeverity.HIGH:
                if rule.allow_if_session_approved and session_id:
                    session_rules = self._session_approved.get(session_id, set())
                    if rule.rule_id in session_rules:
                        return ApprovalGateResult(
                            verdict=ApprovalVerdict.ALLOW,
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            approval_source=APPROVAL_SOURCE_AUTO,
                        )
                return ApprovalGateResult(
                    verdict=ApprovalVerdict.ASK,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    message=rule.message,
                    require_interactive=True,
                    approval_source=APPROVAL_SOURCE_GATE_ASK,
                )

            if rule.severity == ApprovalSeverity.MEDIUM:
                if auto_approve:
                    return ApprovalGateResult(
                        verdict=ApprovalVerdict.ALLOW,
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        message=rule.message,
                        approval_source=APPROVAL_SOURCE_AUTO,
                    )
                if rule.allow_if_session_approved and session_id:
                    session_rules = self._session_approved.get(session_id, set())
                    if rule.rule_id in session_rules:
                        return ApprovalGateResult(
                            verdict=ApprovalVerdict.ALLOW,
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            approval_source=APPROVAL_SOURCE_AUTO,
                        )
                return ApprovalGateResult(
                    verdict=ApprovalVerdict.ASK,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    message=rule.message,
                    require_interactive=False,
                    approval_source=APPROVAL_SOURCE_GATE_ASK,
                )

            if rule.severity == ApprovalSeverity.LOW:
                if rule.allow_if_user_whitelisted and user_id in self._user_whitelist:
                    return ApprovalGateResult(
                        verdict=ApprovalVerdict.ALLOW,
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        approval_source=APPROVAL_SOURCE_AUTO,
                    )
                return ApprovalGateResult(
                    verdict=ApprovalVerdict.ALLOW,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    message=rule.message,
                    approval_source=APPROVAL_SOURCE_NONE,
                )

        return ApprovalGateResult(verdict=ApprovalVerdict.ALLOW, approval_source=APPROVAL_SOURCE_NONE)

    def approve_session_rule(self, session_id: str, rule_id: str) -> bool:
        """Record session approval. Returns False if rule is a hard floor (rejected)."""
        for rule in self._rules:
            if rule.rule_id == rule_id and (
                rule.hard_floor or rule.severity == ApprovalSeverity.CRITICAL
            ):
                logger.warning(
                    "refuse session approval for hard-floor rule %s", rule_id,
                )
                return False
        if session_id not in self._session_approved:
            self._session_approved[session_id] = set()
        self._session_approved[session_id].add(rule_id)
        return True

    def revoke_session_approval(self, session_id: str, rule_id: Optional[str] = None):
        """Revoke session-level approval for one or all rules."""
        if rule_id is None:
            self._session_approved.pop(session_id, None)
        elif session_id in self._session_approved:
            self._session_approved[session_id].discard(rule_id)

    def add_rule(self, rule: ApprovalRule):
        """Programmatically add a custom approval rule."""
        if rule.severity == ApprovalSeverity.CRITICAL:
            rule.hard_floor = True
            rule.allow_if_session_approved = False
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
                "hard_floor": bool(r.hard_floor or r.severity == ApprovalSeverity.CRITICAL),
            }
            for r in self._rules
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Return current gate statistics."""
        return {
            "total_rules": len(self._rules),
            "hard_floor_rules": sum(
                1 for r in self._rules
                if r.hard_floor or r.severity == ApprovalSeverity.CRITICAL
            ),
            "whitelisted_users": len(self._user_whitelist),
            "active_sessions": len(self._session_approved),
            "disabled": self._disabled,
            "hard_floor_disabled": self._hard_floor_disabled,
            "cache_size": len(self._approval_cache),
        }


def build_approval_provenance(
    *,
    source: str,
    rule_id: Optional[str] = None,
    severity: Optional[str] = None,
    hard_floor: bool = False,
    risk_class: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Stable audit payload: who/why an action was gated or allowed."""
    return {
        "source": source or APPROVAL_SOURCE_NONE,
        "rule_id": rule_id,
        "severity": severity,
        "hard_floor": bool(hard_floor),
        "risk_class": risk_class,
        "reason": reason,
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
