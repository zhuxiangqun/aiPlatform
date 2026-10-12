"""Execution-type coercion + default fail-closed for unknown values.

Living Spec: docs/architecture/execution-decision-matrix.md §4 / §7 / §8 E5
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Tuple

logger = logging.getLogger(__name__)

# Always accepted (runtime paths). hybrid is first-class even if YAML enum lags.
_CORE_TYPES: FrozenSet[str] = frozenset(
    {"handler", "hybrid", "prompt", "python_class", "tool_wrapper"}
)

ENV_FAIL_CLOSED = "AIPLAT_EXECUTION_TYPE_FAIL_CLOSED"
ENV_FAIL_OPEN = "AIPLAT_EXECUTION_TYPE_FAIL_OPEN"
ENV_SOFT_DEV = "AIPLAT_EXECUTION_TYPE_SOFT_DEV"
ENV_FAIL_OPEN_REASON = "AIPLAT_EXECUTION_TYPE_FAIL_OPEN_REASON"
ENV_FAIL_OPEN_BY = "AIPLAT_EXECUTION_TYPE_FAIL_OPEN_BY"
ENV_FAIL_OPEN_UNTIL = "AIPLAT_EXECUTION_TYPE_FAIL_OPEN_UNTIL"

_TRUTHY = frozenset({"1", "true", "yes", "y", "on"})
_FALSY = frozenset({"0", "false", "no", "n", "off"})


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUTHY


def _env_falsy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _FALSY


def _parse_until(raw: str) -> Optional[datetime]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def fail_open_governance_status() -> Dict[str, Any]:
    """E5: status of FAIL_OPEN escape hatch (reason / by / until / expiry).

    Active open requires FAIL_OPEN=1 **and** reason + by + until, with until in the future.
    Missing metadata or expired → not authorized (callers must stay fail-closed).
    """
    flag = _env_truthy(ENV_FAIL_OPEN)
    reason = (os.environ.get(ENV_FAIL_OPEN_REASON) or "").strip()
    by = (os.environ.get(ENV_FAIL_OPEN_BY) or "").strip()
    until_raw = (os.environ.get(ENV_FAIL_OPEN_UNTIL) or "").strip()
    until = _parse_until(until_raw)
    now = datetime.now(timezone.utc)
    missing = [k for k, v in (("reason", reason), ("by", by), ("until", until_raw)) if not v]
    expired = bool(until and until <= now)
    until_invalid = bool(until_raw and until is None)
    authorized = bool(flag and not missing and not expired and not until_invalid)
    expires_within_24h = False
    if until and until > now:
        expires_within_24h = (until - now).total_seconds() <= 86400
    return {
        "flag": flag,
        "authorized": authorized,
        "reason": reason,
        "by": by,
        "until": until.isoformat() if until else until_raw,
        "missing": missing,
        "expired": expired,
        "until_invalid": until_invalid,
        "active": authorized,
        "expires_within_24h": expires_within_24h,
    }


def _fail_open_sidecar_path() -> Path:
    home = (os.environ.get("AIPLAT_HOME") or "").strip() or str(Path.home() / ".aiplat")
    return Path(home) / "ops" / "execution_type_fail_open.json"


def record_fail_open_audit(*, source: str = "runtime") -> Dict[str, Any]:
    """Persist E5 audit sidecar under AIPLAT_HOME/ops/. Returns governance status.

    For execution_store audit_log use :func:`record_fail_open_audit_async` from
    async startup (server lifespan).
    """
    status = fail_open_governance_status()
    payload = {
        **status,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    try:
        path = _fail_open_sidecar_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("fail_open sidecar write skipped", exc_info=True)
    if status.get("flag"):
        if status.get("authorized"):
            logger.warning(
                "AIPLAT_EXECUTION_TYPE_FAIL_OPEN authorized by=%s until=%s reason=%s",
                status.get("by"),
                status.get("until"),
                (status.get("reason") or "")[:200],
            )
            if status.get("expires_within_24h"):
                logger.warning(
                    "AIPLAT_EXECUTION_TYPE_FAIL_OPEN expires within 24h (until=%s) — renew or remove",
                    status.get("until"),
                )
        else:
            logger.error(
                "AIPLAT_EXECUTION_TYPE_FAIL_OPEN set but NOT authorized "
                "(missing=%s expired=%s until_invalid=%s) — staying fail-closed",
                status.get("missing"),
                status.get("expired"),
                status.get("until_invalid"),
            )
    return status


async def record_fail_open_audit_async(*, source: str = "startup") -> Dict[str, Any]:
    """Sidecar + async execution_store audit_log (call from server lifespan)."""
    status = record_fail_open_audit(source=source)
    if not status.get("flag"):
        return status
    try:
        from core.services.execution_store import get_execution_store

        store = get_execution_store()
        await store.add_audit_log(
            action="execution_type_fail_open",
            status="ok" if status.get("authorized") else "denied",
            actor_id=str(status.get("by") or "unknown"),
            resource_type="execution_type_policy",
            resource_id="fail_open",
            detail={
                "kind": "execution_type_fail_open",
                "authorized": bool(status.get("authorized")),
                "reason": status.get("reason") or "",
                "until": status.get("until") or "",
                "expired": bool(status.get("expired")),
                "missing": list(status.get("missing") or []),
                "source": source,
            },
        )
    except Exception:
        logger.debug("fail_open audit_log skipped", exc_info=True)
    return status


def execution_type_fail_closed() -> bool:
    """Default fail-closed for unknown execution_type.

    Priority:
    1. Authorized FAIL_OPEN (E5: reason+by+until, not expired) → open
    2. Explicit FAIL_CLOSED=0 / SOFT_DEV=1 → soft (dev opt-in)
    3. Explicit FAIL_CLOSED=1 → closed
    4. Default → closed (safe default; production profile no longer required)
    """
    gov = fail_open_governance_status()
    if gov.get("authorized"):
        return False
    if _env_truthy(ENV_SOFT_DEV) or _env_falsy(ENV_FAIL_CLOSED):
        return False
    if _env_truthy(ENV_FAIL_CLOSED):
        return True
    return True


def _known_and_aliases() -> Tuple[FrozenSet[str], dict]:
    known = set(_CORE_TYPES)
    aliases: dict = {"llm": "prompt", "ai": "prompt", "script": "handler", "code": "handler"}
    try:
        from core.harness.registry.registry_loader import load_execution_types

        reg = load_execution_types()
        for c in reg.canonical or []:
            known.add(str(c).strip().lower())
        for k, v in (reg.aliases or {}).items():
            aliases[str(k).strip().lower()] = str(v).strip().lower()
    except Exception:
        logger.debug("execution_types registry load skipped", exc_info=True)
    return frozenset(known), aliases


def known_execution_types() -> FrozenSet[str]:
    """Canonical set for CI / lint (aliases resolved separately)."""
    known, _ = _known_and_aliases()
    return known


def coerce_execution_type(
    raw: str,
    *,
    skill_name: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """Normalize ``execution_type`` or reject.

    Returns ``(normalized, None)`` on success, or ``(None, error)`` when hard-fail.
    Empty input → ``("", None)`` so callers may auto-detect.
    Unknown: fail-closed (default) → error; soft opt-in → WARNING and ``\"prompt\"``.
    """
    et = str(raw or "").strip().lower()
    if not et:
        return "", None

    known, aliases = _known_and_aliases()
    et = aliases.get(et, et)
    if et in known:
        return et, None

    label = skill_name or "?"
    if execution_type_fail_closed():
        return None, (
            f"Skill '{label}': unknown execution_type={raw!r} "
            f"(known={sorted(known)}; fail-closed — refuse LLM soft-fallback). "
            f"Dev soft: {ENV_SOFT_DEV}=1 or {ENV_FAIL_CLOSED}=0; "
            f"emergency open: {ENV_FAIL_OPEN}=1 + REASON/BY/UNTIL"
        )
    logger.warning(
        "Skill '%s': unknown execution_type=%r — treating as prompt (dev soft-fallback). "
        "Default is fail-closed; unset %s / %s to restore hard-fail.",
        label,
        raw,
        ENV_SOFT_DEV,
        ENV_FAIL_CLOSED,
    )
    return "prompt", None
