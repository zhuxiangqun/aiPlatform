"""Trajectory Collector — structured conversation data for fine-tuning.

Writes each turn as JSONL to ~/.aiplat/trajectories/.
Format: ShareGPT-compatible, suitable for LoRA / SFT training.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.trajectory")

_TRAJ_DIR = Path(os.getenv("AIPLAT_TRAJECTORY_DIR",
    os.path.expanduser("~/.aiplat/trajectories")))


def ensure_dir() -> None:
    _TRAJ_DIR.mkdir(parents=True, exist_ok=True)


def collect_turn(
    session_id: str,
    role: str,
    content: str,
    *,
    tool_name: Optional[str] = None,
    tool_action: Optional[str] = None,
    tool_result: Optional[Any] = None,
) -> None:
    """Record one conversation turn.

    Args:
        session_id: Unique session identifier.
        role: "user" | "assistant" | "tool"
        content: Text content (user query / assistant response).
        tool_name: Tool name (only for role="tool").
        tool_action: Tool action (e.g. "goto", "extract").
        tool_result: Tool result (JSON-serializable).
    """
    try:
        ensure_dir()
        entry: Dict[str, Any] = {
            "id": session_id,
            "role": role,
            "content": content,
            "timestamp": int(time.time()),
        }
        if role == "tool" and tool_name:
            entry["name"] = tool_name
            entry["action"] = tool_action or ""
            entry["result"] = tool_result

        file_path = _TRAJ_DIR / f"{session_id}.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Trajectory save failed: %s", e)


def get_recent_trajectories(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent trajectories for few-shot injection."""
    try:
        ensure_dir()
        files = sorted(_TRAJ_DIR.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
        entries: List[Dict[str, Any]] = []
        for f in files[:limit]:
            with open(f) as fh:
                for line in fh:
                    if line.strip():
                        entries.append(json.loads(line))
                        if len(entries) >= limit * 5:
                            return entries
        return entries
    except Exception:
        return []
