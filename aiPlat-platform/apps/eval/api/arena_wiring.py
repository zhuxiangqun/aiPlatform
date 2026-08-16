"""
Arena wiring — manual-trigger endpoints for Darwin Arena (Elo competition).

Wires the previously-unwired arena subsystem (P0-B3): manual trigger only,
per arena's documented design (no background scheduling to control LLM costs).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body

from core.api.core_facade import (arena_leaderboard, arena_run_round_robin,
                                  wake_agent_start, wake_agent_status,
                                  wake_agent_stop)

router = APIRouter(tags=["arena"])


@router.get("/arena/leaderboard")
async def get_arena_leaderboard() -> Dict[str, Any]:
    """Get Darwin Arena Elo leaderboard (empty before first run)."""
    return {"leaderboard": arena_leaderboard()}


@router.post("/arena/run")
async def run_arena(payload: dict = Body(...)) -> Dict[str, Any]:
    """Manually trigger a round-robin tournament.

    Body:
      - contenders: list of {"name": str, "fn": str} (fn is an opaque
        function identifier used by the deterministic fallback scorer;
        a real benchmark_fn may be injected server-side)
      - matches_per_pair: int (default 3)
    """
    contenders_raw = payload.get("contenders", [])
    contenders = [(str(c.get("name", "")), str(c.get("fn", "")))
                  for c in contenders_raw if isinstance(c, dict)]
    if not contenders:
        return {"error": "contenders required (list of {name, fn})"}
    result = await arena_run_round_robin(
        contenders=contenders,
        matches_per_pair=int(payload.get("matches_per_pair", 3)),
    )
    return result


# ═══════════════════════════════════════════════════════════
# WakeAgent — zero-token filesystem change monitor
# ═══════════════════════════════════════════════════════════

@router.get("/wake-agent/status")
async def get_wake_agent_status() -> Dict[str, Any]:
    """Get WakeAgent filesystem-change monitor status."""
    return {"status": wake_agent_status()}


@router.post("/wake-agent/start")
async def start_wake_agent(payload: dict = Body(...)) -> Dict[str, Any]:
    """Start WakeAgent watching (zero-token checksum polling).

    Body:
      - paths: optional list of paths to watch (default from env)
    """
    return {"status": await wake_agent_start(paths=payload.get("paths"))}


@router.post("/wake-agent/stop")
async def stop_wake_agent() -> Dict[str, Any]:
    """Stop WakeAgent."""
    return {"status": await wake_agent_stop()}
