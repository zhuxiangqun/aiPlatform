"""FDE Quality Summary — cross-subsystem quality bus (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException, Query, Body

import json, asyncio, time, os, hashlib

router = APIRouter(tags=["fde-quality-summary"])


@router.get("/quality-summary", response_model=FdeItemResponse)
async def fde_quality_summary():
    """Cross-subsystem quality aggregation — the Quality Bus.

    Returns per-subsystem quality scores (0-100) and an overall health rating.
    All data sources are read-only and complete in <200ms.
    """
    import time as _t_qs
    t0 = _t_qs.time()

    scores = {}
    overall = 0
    subsystems = 0

    # ── FDE quality ──
    try:
        from .fde import _get_governance_live_status
        live = _get_governance_live_status()
        dr = live.get("delivery_rate", 0)
        ev = live.get("evidence_entity_count", 0)
        ss = live.get("delivery_session_count", 0)
        scores["fde"] = {
            "score": min(100, dr + min(ev * 10, 30)),
            "delivery_rate": dr,
            "evidence_count": ev,
            "sessions": ss,
            "detail": "ok" if ss > 0 else "no_data",
        }
        overall += scores["fde"]["score"]
        subsystems += 1
    except Exception:
        scores["fde"] = {"score": 0, "detail": "error"}

    # ── SECI quality ──
    try:
        from core.api.core_facade import get_seci_engine
        se = get_seci_engine()
        ac = se.get_atom_count()
        lc = se.get_link_count()
        ratio = round(lc / max(ac, 1) * 50)
        scores["seci"] = {
            "score": min(100, ac * 3 + ratio),
            "atoms": ac,
            "links": lc,
            "link_ratio": round(lc / max(ac, 1), 2),
            "detail": "growing" if ac > 0 else "empty",
        }
        overall += scores["seci"]["score"]
        subsystems += 1
    except Exception:
        scores["seci"] = {"score": 0, "detail": "error"}

    # ── Convergence quality ──
    try:
        from .fde import _get_convergence_status
        gov = _get_convergence_status()
        ct = gov.get("applied_triggers", 0)
        scores["convergence"] = {
            "score": min(100, ct * 20 + 20),
            "triggers_fired": ct,
            "config_loaded": gov.get("config_loaded", False),
            "detail": "active" if ct > 0 else "idle",
        }
        overall += scores["convergence"]["score"]
        subsystems += 1
    except Exception:
        scores["convergence"] = {"score": 0, "detail": "error"}

    # ── ContextBus quality ──
    try:
        from .fde import _get_pipeline_health
        pipe = _get_pipeline_health()
        scores["context_bus"] = {
            "score": 100 if pipe == "ok" else 50 if pipe == "degraded" else 0,
            "health": pipe,
            "detail": "ok" if pipe == "ok" else pipe,
        }
        overall += scores["context_bus"]["score"]
        subsystems += 1
    except Exception:
        scores["context_bus"] = {"score": 0, "detail": "error"}

    overall_score = round(overall / max(subsystems, 1))
    rating = "excellent" if overall_score >= 80 else "good" if overall_score >= 60 else "fair" if overall_score >= 40 else "poor"

    return {
        "overall_quality": overall_score,
        "rating": rating,
        "subsystems": scores,
        "elapsed_ms": round((_t_qs.time() - t0) * 1000),
    }
