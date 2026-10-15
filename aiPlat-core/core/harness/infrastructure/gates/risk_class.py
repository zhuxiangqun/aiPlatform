"""Tool risk classes — OpenWorker-inspired intrinsic side-effect taxonomy.

Effective risk drives PolicyGate / ApprovalGate escalation. Overrides may only
*tighten* (raise strictness); relaxing EXTERNAL → READ is rejected.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional

_log = logging.getLogger(__name__)


class RiskClass(str, Enum):
    READ = "read"  # no side effects
    EGRESS = "egress"  # network / outbound data channel
    WRITE_LOCAL = "write_local"  # mutates workspace
    EXEC = "exec"  # runs commands / code
    EXTERNAL = "external"  # side effects off-machine (send, notify, SaaS write)


_STRICTNESS: Dict[RiskClass, int] = {
    RiskClass.READ: 0,
    RiskClass.EGRESS: 1,
    RiskClass.EXTERNAL: 2,
    RiskClass.WRITE_LOCAL: 3,
    RiskClass.EXEC: 3,
}

# Built-in name → class (extend via register_risk / env later; keep small).
_BASE: Dict[str, RiskClass] = {
    "shell_exec": RiskClass.EXEC,
    "code_execution": RiskClass.EXEC,
    "file_operations": RiskClass.WRITE_LOCAL,
    "repo": RiskClass.WRITE_LOCAL,
    "database": RiskClass.WRITE_LOCAL,
    "http": RiskClass.EGRESS,
    "web_fetch": RiskClass.EGRESS,
    "web_search": RiskClass.EGRESS,
    "browser": RiskClass.EGRESS,
    "browser_open_url": RiskClass.EGRESS,
    "email": RiskClass.EXTERNAL,
    "slack": RiskClass.EXTERNAL,
    "notifier": RiskClass.EXTERNAL,
    "process": RiskClass.EXEC,
    "permission_*": RiskClass.EXTERNAL,
    "agent_manager": RiskClass.EXTERNAL,
    "sysgraph_tools": RiskClass.EXTERNAL,
}

RiskOverrides = Callable[[str], Optional[RiskClass]]


def strictness(rc: RiskClass) -> int:
    return _STRICTNESS.get(rc, 0)


def cannot_relax(base: RiskClass, override: RiskClass) -> bool:
    """True if override is strictly tighter or equal (allowed)."""
    return strictness(override) >= strictness(base)


def classify(
    tool_name: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    overrides: Optional[RiskOverrides] = None,
) -> RiskClass:
    """Resolve effective risk for a tool name.

    Order: override (tighten-only) → exact base → glob-ish prefix_* → metadata
    ``requires_approval`` / ``risk_class`` → READ default.
    """
    name = str(tool_name or "").strip()
    base = _lookup_base(name)

    if overrides is not None:
        ov = overrides(name)
        if ov is not None:
            if cannot_relax(base, ov):
                return ov
            # Reject relaxation — keep base (OpenWorker floor rule).
            return base

    meta = metadata or {}
    raw = meta.get("risk_class") or meta.get("risk")
    if isinstance(raw, str) and raw.strip():
        try:
            from_meta = RiskClass(raw.strip().lower())
            if cannot_relax(base, from_meta):
                return from_meta
            return base
        except ValueError:
            _log.debug("unknown risk_class metadata %r for tool %s", raw, name)
    if meta.get("requires_approval") is True and base == RiskClass.READ:
        return RiskClass.EXTERNAL

    return base


def _lookup_base(name: str) -> RiskClass:
    if name in _BASE:
        return _BASE[name]
    for key, rc in _BASE.items():
        if key.endswith("*") and name.startswith(key[:-1]):
            return rc
    return RiskClass.READ


def register_risk(tool_name: str, risk: RiskClass) -> None:
    """Register or tighten a built-in mapping (tests / plugins)."""
    existing = _BASE.get(tool_name)
    if existing is not None and not cannot_relax(existing, risk):
        raise ValueError(
            f"cannot relax risk for {tool_name}: {existing.value} → {risk.value}"
        )
    _BASE[tool_name] = risk


def is_hard_floor_risk(rc: RiskClass) -> bool:
    """EXEC and WRITE_LOCAL crown jewels — always human-gated when matched CRITICAL."""
    return rc in (RiskClass.EXEC, RiskClass.WRITE_LOCAL, RiskClass.EXTERNAL)
