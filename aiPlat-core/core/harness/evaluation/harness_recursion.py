"""Contrastive harness step and improvement library.

Public surface used by stage reflection, team brain, and the duty board.
Library entries stay empty until a contrast step commits evidence.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

COMPONENT_KINDS = frozenset({
    "guardrail",
    "system_prompt",
    "plugin",
    "script",
    "tool_guidance",
    "memory",
    "skill",
    "subagent",
})

CONTRAST_STATE_KEYS = (
    "_tool_receipts",
    "_pseudo_tool",
    "_output_empty",
    "_output_files",
    "_reopened_outputs",
    "_no_reopen",
)

_FILE_BLOCK = re.compile(r"(?m)^##\s*FILE:\s*(\S+)")


def recursion_budget() -> int:
    """Task-level probe budget. Default 1; clamp 1..5."""
    try:
        n = int(os.environ.get("AIPLAT_HARNESS_RECURSION_BUDGET", "1"))
    except ValueError:
        n = 1
    return max(1, min(5, n))


def library_path() -> Path:
    from core.utils.paths import get_aiplat_data_dir

    return Path(get_aiplat_data_dir("eval/harness_improvement_library.json"))


def _load() -> List[Dict[str, Any]]:
    path = library_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def recall_library(query: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    """Return reusable components plus when/why text. Never a whole-harness inherit."""
    rows = _load()
    q = (query or "").strip().lower()
    if q:
        rows = [
            r for r in rows
            if q in str(r.get("experience") or "").lower()
            or q in str(r.get("task_id") or "").lower()
        ]
    return rows[: max(0, int(limit))]


def summarize_library(recent: int = 5) -> Dict[str, Any]:
    """Duty-board slice. Counts only; does not invent a success rate."""
    rows = _load()
    return {
        "available": bool(rows),
        "library_entries": len(rows),
        "pending_traces": 0,
        "inherit_whole": False,
        "recent": rows[: max(0, int(recent))],
    }


def format_library_overlay(rows: Sequence[Dict[str, Any]], max_components: int = 6) -> Optional[str]:
    """Next-task overlay. The public harness stays; components are optional."""
    lines: List[str] = []
    for row in list(rows)[: max_components]:
        exp = str(row.get("experience") or "").strip()
        if exp:
            lines.append(exp)
    return "\n".join(lines) if lines else None


def clear_contrast_signals(state: Dict[str, Any]) -> None:
    """Drop contrast flags so the next stage cannot reuse this run's events."""
    if not isinstance(state, dict):
        return
    for key in CONTRAST_STATE_KEYS:
        state.pop(key, None)


def copy_contrast_signals(context: Dict[str, Any], state: Dict[str, Any]) -> None:
    """Copy contrast flags from the loop context onto the pipeline state."""
    if not isinstance(context, dict) or not isinstance(state, dict):
        return
    surface_contrast_signals(context)
    for key in CONTRAST_STATE_KEYS:
        if key in context:
            state[key] = context[key]


def surface_contrast_signals(context: Dict[str, Any]) -> None:
    """Fill contrast flags from receipts already on the loop context."""
    if not isinstance(context, dict):
        return
    receipts = context.get("_tool_receipts")
    if isinstance(receipts, list) and receipts:
        context["_tool_receipts"] = receipts


def file_paths_from_text(text: str) -> List[str]:
    """Paths declared as ``## FILE:`` blocks in stage or skill text."""
    return [m.group(1).strip() for m in _FILE_BLOCK.finditer(text or "")]


def events_from_state(state: Dict[str, Any]) -> List[Dict[str, str]]:
    if not isinstance(state, dict):
        return []
    out: List[Dict[str, str]] = []
    if state.get("_output_empty"):
        out.append({"type": "empty_output", "key": "output"})
    if state.get("_pseudo_tool"):
        out.append({"type": "pseudo_tool", "key": "tool"})
    return out


def step_from_state(
    state: Dict[str, Any],
    commit: bool = False,
    stage_id: str = "",
) -> Optional[Dict[str, Any]]:
    """Pair this run's contrast events. Does not write the library unless commit is set."""
    events = events_from_state(state if isinstance(state, dict) else {})
    if not events:
        return None
    step = {"stage_id": stage_id, "events": events, "committed": False}
    if commit:
        logger.debug("harness recursion commit skipped: no composed components")
    return step


def run_contrastive_step(payload: Dict[str, Any], commit: bool = False) -> Dict[str, Any]:
    """Compose probes for one task. Without gold or probes, return an empty step."""
    probes = payload.get("probes") if isinstance(payload, dict) else None
    items = probes if isinstance(probes, list) else []
    budget = recursion_budget()
    return {
        "probes": min(len(items), budget),
        "budget": budget,
        "committed": False,
        "components": [],
    }
