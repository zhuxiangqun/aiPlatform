"""Optional handler for Phase 1b bridge smoke (deterministic)."""

from __future__ import annotations

from typing import Any, Dict


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "marker": "AIPLAT_DEMO_HANDLER_OK",
        "params": params or {},
    }
