"""Move contrast flags between loop context and pipeline state.

Evaluation code must stay pure. Callers: stage_runner, stage_reflection, pipeline_engine.
"""

from __future__ import annotations

from typing import Any, Dict

from core.harness.evaluation.harness_recursion import CONTRAST_STATE_KEYS


def clear_contrast_signals(state: Dict[str, Any]) -> None:
    """Drop contrast flags so the next stage cannot reuse this run's events."""
    if not isinstance(state, dict):
        return
    for key in CONTRAST_STATE_KEYS:
        state.pop(key, None)


def surface_contrast_signals(context: Dict[str, Any]) -> None:
    """Fill contrast flags from receipts already on the loop context."""
    if not isinstance(context, dict):
        return
    receipts = context.get("_tool_receipts")
    if isinstance(receipts, list) and receipts:
        context["_tool_receipts"] = receipts


def copy_contrast_signals(context: Dict[str, Any], state: Dict[str, Any]) -> None:
    """Copy contrast flags from the loop context onto the pipeline state."""
    if not isinstance(context, dict) or not isinstance(state, dict):
        return
    surface_contrast_signals(context)
    for key in CONTRAST_STATE_KEYS:
        if key in context:
            state[key] = context[key]
