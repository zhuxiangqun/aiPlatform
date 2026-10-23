"""Slice offline policy evaluator (pi-thin-offline.md / KG-FAULT-01 #4).

Enforces TTL and denied_ops for five-products first slice. Does not replace
Pi runtime gates — provides an auditable server-side check for WP4 evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Sequence

# Defaults aligned with reports/five-products/contracts/pi-thin-offline.md
DEFAULT_OFFLINE_MAX_TTL_HOURS = 24.0
DEFAULT_SHORTENED_TTL_HOURS = 12.0  # no revocation channel
DEFAULT_DENIED_OPS = frozenset(
    {
        "write_production",
        "cross_tenant",
        "export_secrets",
        "arbitrary_shell",
        "heal",
        "auto_repair",
        "undeclared_tool",
    }
)


def _parse_ts(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def evaluate_slice_offline_policy(
    *,
    last_bundle_validated_at: str,
    now: Optional[str] = None,
    requested_ops: Optional[Sequence[str]] = None,
    has_revocation_channel: bool = False,
    offline_max_ttl_hours: Optional[float] = None,
    shortened_ttl_hours: Optional[float] = None,
    denied_ops: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Return ok/deny decision for offline execution window.

    - No revocation channel → use shortened TTL (default 12h).
    - Past TTL → deny (stop execution), not degrade-to-readonly success.
    - Any requested op in denied set → deny.
    """
    denied_set = set(denied_ops) if denied_ops is not None else set(DEFAULT_DENIED_OPS)
    if has_revocation_channel:
        ttl_h = float(
            DEFAULT_OFFLINE_MAX_TTL_HOURS
            if offline_max_ttl_hours is None
            else offline_max_ttl_hours
        )
    else:
        ttl_h = float(
            DEFAULT_SHORTENED_TTL_HOURS
            if shortened_ttl_hours is None
            else shortened_ttl_hours
        )

    last = _parse_ts(last_bundle_validated_at)
    if last is None:
        return {
            "ok": False,
            "decision": "deny",
            "reason": "invalid_or_missing_last_bundle_validated_at",
            "ttl_hours": ttl_h,
        }

    now_dt = _parse_ts(now) if now else datetime.now(timezone.utc)
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    age = now_dt - last
    ttl = timedelta(hours=ttl_h)
    ops = [str(x).strip() for x in (requested_ops or []) if str(x).strip()]
    hit_denied = sorted({op for op in ops if op in denied_set})

    if age > ttl:
        return {
            "ok": False,
            "decision": "deny",
            "reason": "offline_ttl_exceeded",
            "ttl_hours": ttl_h,
            "age_seconds": age.total_seconds(),
            "has_revocation_channel": has_revocation_channel,
            "requested_ops": ops,
        }

    if hit_denied:
        return {
            "ok": False,
            "decision": "deny",
            "reason": "denied_ops",
            "denied_ops_hit": hit_denied,
            "ttl_hours": ttl_h,
            "age_seconds": age.total_seconds(),
            "requested_ops": ops,
        }

    return {
        "ok": True,
        "decision": "allow",
        "reason": "within_ttl_and_ops_allowed",
        "ttl_hours": ttl_h,
        "age_seconds": age.total_seconds(),
        "has_revocation_channel": has_revocation_channel,
        "requested_ops": ops,
    }
