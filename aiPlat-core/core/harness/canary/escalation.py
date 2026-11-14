"""
Canary escalation policy (pure functions).

This module is intentionally dependency-free so it can be unit tested.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple


def change_id_for_canary(canary_id: str) -> str:
    """Deterministic change_id for a canary stream so that Change Control UI aggregates events.

    Args:
        canary_id: canary 标识。
    """
    cid = str(canary_id or "").strip() or "unknown"
    h = hashlib.sha1(cid.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"chg-canary-{h}"


def change_id_for_release_candidate(candidate_id: str) -> str:
    """Deterministic change_id for a release candidate.

    Args:
        candidate_id: candidate 标识。
    """
    cid = str(candidate_id or "").strip() or "unknown"
    h = hashlib.sha1(cid.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"chg-rc-{h}"


def is_p0_report(report: Any) -> bool:
    """True if report contains a P0 issue.

    Args:
        report: report 参数。
    """
    if not isinstance(report, dict):
        return False
    issues = report.get("issues")
    if not isinstance(issues, list):
        return False
    for it in issues[:200]:
        if not isinstance(it, dict):
            continue
        sev = str(it.get("severity") or "").strip().upper()
        if sev == "P0":
            return True
    return False


def consecutive_failures_from_reports(recent_canary_reports: List[Dict[str, Any]]) -> int:
    """recent_canary_reports: newest-first list of canary_report payload dicts.

    Args:
        recent_canary_reports: recent_canary_reports 参数。
    """
    n = 0
    for r in recent_canary_reports:
        if not isinstance(r, dict):
            continue
        # canonical: pass boolean; fallback to status
        p = r.get("pass")
        if isinstance(p, bool):
            ok = p
        else:
            st = str(r.get("status") or "").lower()
            ok = st in {"completed", "success", "ok"}
        if ok:
            break
        n += 1
    return n


def should_escalate(
    *,
    enabled: bool,
    p0_only: bool,
    consecutive_failures_threshold: int,
    new_report: Dict[str, Any],
    new_consecutive_failures: int,
) -> bool:
    """should_escalate。

    Args:
        enabled: 是否启用。
        p0_only: p0_only 参数。
        consecutive_failures_threshold: consecutive_failures_threshold 参数。
        new_report: new_report 参数。
        new_consecutive_failures: new_consecutive_failures 参数。
    """
    if not enabled:
        return False
    if bool(consecutive_failures_threshold) and int(new_consecutive_failures) < int(consecutive_failures_threshold):
        return False
    if p0_only and not is_p0_report(new_report):
        return False
    return True
