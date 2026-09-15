"""FDE usage signals (S1–S4) — platform-observable adoption metrics from action_audit.

Contract: docs/contracts/FDE_USAGE_SIGNAL_MINIMAL_SET.md
Does not compute customer ROI; honest unavailable when domain missing or store fails.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _empty(domain_id: str, status: str = "unavailable") -> Dict[str, Any]:
    return {
        "domain_id": domain_id or "",
        "dau_today": 0,
        "calls_today": 0,
        "success_rate_today": None,
        "active_days_30d": 0,
        "status": status,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_usage_signal(
    domain_id: str,
    *,
    store: Any = None,
    require_domain: bool = True,
) -> Dict[str, Any]:
    """Return S1–S4 snapshot for ``domain_id``."""
    domain = (domain_id or "").strip()
    if not domain:
        return _empty("")

    if require_domain:
        try:
            from core.harness.knowledge.domain_router import DomainRouter

            DomainRouter().require_known_domain(domain)
        except Exception as e:
            logger.info("usage_signal: domain check failed for %s: %s", domain, e)
            out = _empty(domain, status="unavailable")
            out["error"] = str(e)[:160]
            return out

    try:
        st = store
        if st is None:
            from core.harness.ontology_engine.action_registry import get_action_registry

            st = get_action_registry()._store
            await st.initialize()
        row = await st.query_usage_signal(domain)
        row = dict(row)
        row["computed_at"] = datetime.now(timezone.utc).isoformat()
        row.setdefault("status", "ok")
        return row
    except Exception as e:
        logger.warning("usage_signal query failed: %s", e)
        out = _empty(domain, status="unavailable")
        out["error"] = str(e)[:160]
        return out


async def get_usage_trend(
    domain_id: str,
    days: int = 30,
    *,
    store: Any = None,
    require_domain: bool = True,
) -> Dict[str, Any]:
    """Return per-day trend points for Tab⑧."""
    domain = (domain_id or "").strip()
    if not domain:
        return {"domain_id": "", "days": days, "points": [], "status": "unavailable"}

    if require_domain:
        try:
            from core.harness.knowledge.domain_router import DomainRouter

            DomainRouter().require_known_domain(domain)
        except Exception as e:
            return {
                "domain_id": domain,
                "days": days,
                "points": [],
                "status": "unavailable",
                "error": str(e)[:160],
            }

    try:
        st = store
        if st is None:
            from core.harness.ontology_engine.action_registry import get_action_registry

            st = get_action_registry()._store
            await st.initialize()
        points: List[Dict[str, Any]] = await st.query_usage_trend(domain, days=days)
        return {
            "domain_id": domain,
            "days": days,
            "points": points,
            "status": "ok",
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
    except ValueError as e:
        return {
            "domain_id": domain,
            "days": days,
            "points": [],
            "status": "unavailable",
            "error": str(e)[:160],
        }
    except Exception as e:
        logger.warning("usage_trend query failed: %s", e)
        return {
            "domain_id": domain,
            "days": days,
            "points": [],
            "status": "unavailable",
            "error": str(e)[:160],
        }


def _store_default() -> Any:
    from core.harness.ontology_engine.action_registry import get_action_registry

    return get_action_registry()._store


async def get_usage_baseline(
    domain_id: str, *, store: Any = None
) -> Optional[Dict[str, Any]]:
    domain = (domain_id or "").strip()
    if not domain:
        return None
    try:
        st = store or _store_default()
        await st.initialize()
        row = await st.get_usage_baseline(domain)
        return dict(row) if row else None
    except Exception as e:
        logger.warning("get_usage_baseline failed: %s", e)
        return None


async def capture_usage_baseline(
    domain_id: str,
    *,
    days: int = 30,
    captured_by: str = "fde",
    store: Any = None,
) -> Dict[str, Any]:
    domain = (domain_id or "").strip()
    if not domain:
        return {"status": "unavailable", "error": "domain_id required"}
    try:
        st = store or _store_default()
        await st.initialize()
        row = await st.capture_usage_baseline_from_trend(
            domain, days=days, captured_by=captured_by
        )
        out = dict(row)
        out["status"] = "ok"
        return out
    except Exception as e:
        logger.warning("capture_usage_baseline failed: %s", e)
        return {"domain_id": domain, "status": "unavailable", "error": str(e)[:160]}
