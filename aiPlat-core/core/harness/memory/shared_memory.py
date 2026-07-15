"""
Shared Memory — cross-instance collective learnings.

Enables multiple Agent instances to share knowledge via a
central JSON file (~/.aiplat/memory/shared/learnings.json).

Mechanism:
  - Write: append/overwrite keyed learnings with confidence-based dedup
  - Read: inject as prompt context at Agent startup
  - Override: high-confidence entries are NOT replaced by low-confidence ones

Design from "plur" concept — collective Agent brain across instances.
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from core.utils.paths import get_aiplat_data_dir

_SHARED_DIR = get_aiplat_data_dir("memory/shared")
_LEARNINGS_PATH = _os.path.join(_SHARED_DIR, "learnings.json")


@dataclass
class SharedLearning:
    key: str
    value: Any
    source_agent: str = ""
    source_session: str = ""
    confidence: str = "medium"          # high | medium | low
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source_agent": self.source_agent,
            "source_session": self.source_session,
            "confidence": self.confidence,
            "timestamp": self.timestamp or _time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", _time.gmtime(),
            ),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SharedLearning":
        return cls(
            key=d.get("key", ""),
            value=d.get("value", ""),
            source_agent=d.get("source_agent", ""),
            source_session=d.get("source_session", ""),
            confidence=d.get("confidence", "medium"),
            timestamp=d.get("timestamp", ""),
        )


def _load_all() -> List[SharedLearning]:
    u"""Load all shared learnings from the JSON file."""
    if not _os.path.exists(_LEARNINGS_PATH):
        return []
    try:
        data = _json.load(open(_LEARNINGS_PATH, "r", encoding="utf-8"))
        return [SharedLearning.from_dict(e) for e in data.get("entries", [])]
    except Exception:
        return []


def _save_all(entries: List[SharedLearning]) -> None:
    u"""Save all shared learnings to the JSON file."""
    _os.makedirs(_SHARED_DIR, exist_ok=True)
    with open(_LEARNINGS_PATH, "w", encoding="utf-8") as f:
        _json.dump({
            "version": 1,
            "updated_at": _time.time(),
            "entries": [e.to_dict() for e in entries],
        }, f, indent=2, ensure_ascii=False)


def record_learning(
    key: str,
    value: Any,
    *,
    source_agent: str = "",
    source_session: str = "",
    confidence: str = "medium",
) -> SharedLearning:
    u"""Record a shared learning, with confidence-based dedup.

    Rules:
      - high confidence overwrites medium/low for the same key
      - medium overwrites low
      - low never overwrites anything
      - Same key + same value → skip (no duplicate)
    """
    entries = _load_all()
    learning = SharedLearning(
        key=key, value=value, source_agent=source_agent,
        source_session=source_session, confidence=confidence,
    )

    for i, existing in enumerate(entries):
        if existing.key != key:
            continue
        # Same value → skip
        if str(existing.value) == str(value):
            return existing
        # Confidence-based override
        rank = {"high": 3, "medium": 2, "low": 1}
        if rank.get(learning.confidence, 1) > rank.get(existing.confidence, 1):
            entries[i] = learning
            _save_all(entries)
            return learning
        # Lower confidence → don't override
        return existing

    entries.append(learning)
    _save_all(entries)
    return learning


def get_learnings_context(max_entries: int = 15) -> str:
    u"""Get shared learnings formatted as Agent prompt context.

    Returns empty string if no learnings exist.
    """
    entries = _load_all()
    if not entries:
        return ""

    # Sort by confidence (high first) then recency
    rank = {"high": 3, "medium": 2, "low": 1}
    entries.sort(key=lambda e: (rank.get(e.confidence, 1), e.timestamp), reverse=True)

    lines = ["## Collective Learnings (shared across all agents)"]
    for e in entries[:max_entries]:
        lines.append(
            f"- {e.key}: {e.value} "
            f"(from {e.source_agent or 'unknown'}, confidence={e.confidence})"
        )
    return "\n".join(lines) + "\n"


def extract_learnings_from_state(
    state: Dict[str, Any],
    *,
    source_agent: str = "",
    source_session: str = "",
) -> List[SharedLearning]:
    u"""Extract learnings from pipeline state after execution.

    Scans for:
      - _assess_* results that passed (confidence=high)
      - _shared_state_board entries marked as done
      - error patterns worth remembering
    """
    results = []

    # Passed assessments → high-confidence learnings
    for k, v in state.items():
        if k.startswith("_assess_") and isinstance(v, dict):
            if v.get("overall") == "PASS":
                results.append(SharedLearning(
                    key=f"stage_pass:{k}",
                    value=str(v.get("summary", ""))[:200],
                    source_agent=source_agent,
                    source_session=source_session,
                    confidence="high",
                ))

    # Error patterns → medium-confidence warnings
    error = state.get("error", "")
    if error:
        results.append(SharedLearning(
            key=f"error_pattern:{str(error)[:60]}",
            value="encountered",
            source_agent=source_agent,
            source_session=source_session,
            confidence="medium",
        ))

    # Markings propagated → note
    if state.get("_propagated_markings"):
        results.append(SharedLearning(
            key="markings_propagated",
            value=str(state["_propagated_markings"])[:200],
            source_agent=source_agent,
            confidence="low",
        ))

    return results
