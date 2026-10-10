"""Same-profile code-review gold gate (ReviewBench discipline).

When model / high-risk agent config changes, require a recent gold eval on the
**same noise profile** (low_noise / balanced / high_coverage) before treating
the change as green. Reuses code_review_gold JSONL — no parallel store.

Production callers: compute_agent_diff (attach), CoreFacade.evaluate_gold_profile_gate,
optional canary / HITL review.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional, Sequence

logger = logging.getLogger(__name__)

ENV_GATE = "AIPLAT_GOLD_PROFILE_GATE"  # auto|on|off — default auto (high-risk only)
ENV_MAX_AGE_H = "AIPLAT_GOLD_GATE_MAX_AGE_HOURS"  # default 168 (7d)
ENV_MAX_P0_MISS = "AIPLAT_GOLD_GATE_MAX_P0_MISS"  # default 0.25
DEFAULT_PROFILES = ("low_noise", "balanced", "high_coverage")


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def gate_mode() -> str:
    """auto | on | off"""
    raw = (os.environ.get(ENV_GATE) or "auto").strip().lower()
    if raw in ("off", "0", "false", "no", "disabled"):
        return "off"
    if raw in ("on", "1", "true", "yes", "force"):
        return "on"
    return "auto"


def _max_age_hours() -> float:
    try:
        return max(1.0, float(os.environ.get(ENV_MAX_AGE_H) or 168))
    except (TypeError, ValueError):
        return 168.0


def _max_p0_miss() -> float:
    try:
        return min(1.0, max(0.0, float(os.environ.get(ENV_MAX_P0_MISS) or 0.25)))
    except (TypeError, ValueError):
        return 0.25


def _parse_written_at(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        try:
            # 20261009T120000Z or ISO
            if s.endswith("Z") and "T" in s and len(s) >= 16:
                return datetime.strptime(s[:15], "%Y%m%dT%H%M%S").timestamp()
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None


def _normalize_profile(profile: str) -> str:
    p = (profile or "balanced").strip().lower()
    if p not in DEFAULT_PROFILES:
        return "balanced"
    return p


def _latest_for_profile(
    reports: Sequence[Dict[str, Any]],
    profile: str,
) -> Optional[Dict[str, Any]]:
    want = _normalize_profile(profile)
    for row in reversed(list(reports or [])):
        if not isinstance(row, dict):
            continue
        rp = str(row.get("profile") or "").strip().lower()
        if rp == want or (not rp and want == "balanced"):
            return row
    return None


def evaluate_gold_profile_gate(
    *,
    profile: str = "balanced",
    risk_level: str = "low",
    tenant_id: str = "",
    reports: Optional[Sequence[Dict[str, Any]]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Gate verdict for same-profile gold regression.

    Returns:
      verdict: skip | pass | require_eval | block_regression
      ok: True when change may proceed (skip/pass)
    """
    mode = gate_mode()
    risk = (risk_level or "low").strip().lower()
    prof = _normalize_profile(profile)
    should = force or mode == "on" or (mode == "auto" and risk == "high")
    base = {
        "ok": True,
        "verdict": "skip",
        "profile": prof,
        "risk_level": risk,
        "mode": mode,
        "reason": "",
        "latest": None,
        "gold_regression": None,
        "thresholds": {
            "max_age_hours": _max_age_hours(),
            "max_p0_miss": _max_p0_miss(),
        },
    }
    if not should:
        base["reason"] = f"gate idle (mode={mode}, risk={risk})"
        return base

    rows = list(reports) if reports is not None else []
    if reports is None:
        try:
            from core.harness.evaluation.code_review_gold import list_eval_reports

            rows = list(list_eval_reports(tenant_id=tenant_id or "", limit=40) or [])
        except Exception as e:
            logger.debug("gold_profile_gate load skipped: %s", e, exc_info=True)
            rows = []

    from core.harness.meta.org_harness_metrics import summarize_gold_regression

    def _same_profile(row: Dict[str, Any]) -> bool:
        rp = str(row.get("profile") or "").strip().lower()
        if not rp:
            return prof == "balanced"
        return rp == prof

    same = [r for r in rows if isinstance(r, dict) and _same_profile(r)]
    gold = summarize_gold_regression(same if same else [])
    latest = _latest_for_profile(rows, prof)
    base["gold_regression"] = gold
    base["latest"] = (
        {k: latest.get(k) for k in (
            "precision", "recall", "p0_recall", "novel_count", "written_at", "profile",
        )}
        if latest else None
    )

    if latest is None:
        base["ok"] = False
        base["verdict"] = "require_eval"
        base["reason"] = (
            f"no gold report for profile={prof}; run "
            f"run_code_review_gold_eval(profile={prof!r}) before promoting model/prompt change"
        )
        return base

    # Freshness
    ts = _parse_written_at(latest.get("written_at"))
    age_h = None
    if ts is not None:
        age_h = max(0.0, (time.time() - ts) / 3600.0)
        base["latest"]["age_hours"] = round(age_h, 2)
        if age_h > _max_age_hours():
            base["ok"] = False
            base["verdict"] = "require_eval"
            base["reason"] = (
                f"gold report stale for profile={prof}: age_hours={age_h:.1f} "
                f"> max={_max_age_hours()}"
            )
            return base

    # Regression / P0 miss
    if gold.get("regressing"):
        base["ok"] = False
        base["verdict"] = "block_regression"
        base["reason"] = f"gold regressing on profile={prof} (P/R/P0 delta < -0.02)"
        return base

    miss = gold.get("p0_miss_rate")
    if miss is not None and float(miss) > _max_p0_miss():
        base["ok"] = False
        base["verdict"] = "block_regression"
        base["reason"] = (
            f"p0_miss_rate={miss} > max={_max_p0_miss()} on profile={prof}"
        )
        return base

    # Harness factor drift warning (still pass metrics, but flag)
    factor_delta = gold.get("harness_factor_delta") or {}
    if factor_delta:
        base["harness_factor_delta"] = factor_delta
        base["reason"] = (
            f"same-profile gold ok (profile={prof}); "
            f"harness factors changed: {', '.join(list(factor_delta)[:6])}"
        )
    else:
        base["reason"] = f"same-profile gold ok (profile={prof})"
    factor_delta = gold.get("harness_factor_delta") or {}
    if factor_delta:
        base["harness_factor_delta"] = factor_delta
        base["harness_drift_warning"] = (
            "harness knobs changed since last gold run — attribute score shifts "
            f"to factors {sorted(factor_delta.keys())[:8]} before blaming the model"
        )
    base["ok"] = True
    base["verdict"] = "pass"
    return base


def attach_gold_gate_to_diff(diff: Dict[str, Any], *, profile: str = "balanced", tenant_id: str = "") -> Dict[str, Any]:
    """Mutate/return agent config diff with gold_gate field."""
    out = dict(diff or {})
    risk = str(out.get("risk_level") or "low")
    # Prefer balanced unless caller sets AIPLAT_GOLD_GATE_PROFILE
    prof = (os.environ.get("AIPLAT_GOLD_GATE_PROFILE") or profile or "balanced").strip()
    out["gold_gate"] = evaluate_gold_profile_gate(
        profile=prof,
        risk_level=risk,
        tenant_id=tenant_id,
    )
    return out
