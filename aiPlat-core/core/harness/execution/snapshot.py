"""
Phase 25: ExecutionSnapshot — reproducible execution environment snapshots.

Captures full pipeline execution context (state, configs, strategy metadata)
for before/after comparison of self-healing strategies.

Key insight for L5: reproducible snapshots are the prerequisite for strategy search.
Without them, comparing "rotate_credential vs backoff_retry" is comparing apples to oranges.

Storage: ~/.aiplat/snapshots/{session_id}/{snapshot_id}.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.execution_snapshot")

SNAPSHOT_ROOT = os.path.expanduser("~/.aiplat/snapshots")
MAX_SNAPSHOTS_PER_SESSION = 50


@dataclass
class ExecutionSnapshot:
    """Lightweight snapshot header + reference to full state on disk."""

    snapshot_id: str
    session_id: str
    stage_id: str
    strategy_name: str
    phase: str
    state_summary: Dict[str, Any]  # tokens, iteration, artifacts, error type
    agent_configs: Dict[str, Any]  # agent_type, prompt_extra preview
    timestamp: float = field(default_factory=time.time)

    # Disk path for full state JSON
    _state_path: Optional[str] = field(default=None, repr=False)

    @property
    def full_state(self) -> Optional[Dict[str, Any]]:
        if self._state_path and os.path.exists(self._state_path):
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load snapshot state: %s", e)
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("_state_path", None)
        d["has_full_state"] = bool(self._state_path and os.path.exists(self._state_path))
        return d


def _snapshot_dir(session_id: str) -> str:
    path = os.path.join(SNAPSHOT_ROOT, session_id)
    os.makedirs(path, exist_ok=True)
    return path


def _snapshot_id(session_id: str, strategy_name: str, timestamp: float) -> str:
    raw = f"{session_id}:{strategy_name}:{timestamp}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _extract_state_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract lightweight summary from full pipeline state."""
    return {
        "tokens_used": state.get("tokens_used", 0),
        "tokens_budget": state.get("tokens_budget", 0),
        "iteration": state.get("iteration", 0),
        "phase": state.get("phase", ""),
        "auto_retry_count": state.get("_auto_retry_count", 0),
        "error": str(state.get("error", ""))[:200] if state.get("error") else "",
        "artifacts": {
            k: (bool(v) if not isinstance(v, (dict, list)) else len(str(v)))
            for k, v in state.items()
            if k.startswith("_output_") or (isinstance(v, dict) and v.get("raw_output"))
        },
        "classified_error": state.get("_last_classified_error"),
        "healing_diagnosis": state.get("_meta_diagnosis", ""),
    }


def _extract_agent_configs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract agent configuration fingerprints."""
    configs = {}
    for key in ("_agent_type", "_prompt_extra_hash", "_stage_model"):
        if key in state:
            configs[key] = state[key]
    return configs


def save_execution_snapshot(
    state: Dict[str, Any],
    strategy_name: str,
    *,
    session_id: str = "",
    stage_id: str = "",
) -> Optional[str]:
    """Save a full execution snapshot to disk. Returns snapshot_id or None."""
    if not session_id:
        session_id = state.get("session_id", "") or state.get("_last_error_stage", "")
    if not session_id:
        logger.warning("ExecutionSnapshot: no session_id, skipping")
        return None

    ts = time.time()
    sid = _snapshot_id(session_id, strategy_name, ts)
    dstdir = _snapshot_dir(session_id)
    state_path = os.path.join(dstdir, f"{sid}.json")

    snap = ExecutionSnapshot(
        snapshot_id=sid,
        session_id=session_id,
        stage_id=stage_id or state.get("_last_error_stage", ""),
        strategy_name=strategy_name,
        phase=state.get("phase", "unknown"),
        state_summary=_extract_state_summary(state),
        agent_configs=_extract_agent_configs(state),
        timestamp=ts,
        _state_path=state_path,
    )

    # Write header (metadata JSON)
    header_path = os.path.join(dstdir, f"{sid}.header.json")
    try:
        with open(header_path, "w", encoding="utf-8") as f:
            json.dump(snap.to_dict(), f, ensure_ascii=False, indent=2, default=str)
    except OSError as e:
        logger.warning("ExecutionSnapshot: write header failed: %s", e)
        return None

    # Write full state JSON
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(dict(state), f, ensure_ascii=False, indent=2, default=str)
    except OSError as e:
        logger.warning("ExecutionSnapshot: write full state failed: %s", e)
        return None

    # Prune old snapshots
    _prune_session_snapshots(session_id, max_keep=MAX_SNAPSHOTS_PER_SESSION)

    logger.info(
        "[snapshot] saved: id=%s strategy=%s session=%s tokens=%d",
        sid, strategy_name, session_id, snap.state_summary.get("tokens_used", 0),
    )
    return sid


def load_execution_snapshot(snapshot_id: str, session_id: str) -> Optional[ExecutionSnapshot]:
    """Load a snapshot by ID."""
    header_path = os.path.join(_snapshot_dir(session_id), f"{snapshot_id}.header.json")
    if not os.path.exists(header_path):
        logger.warning("ExecutionSnapshot: header not found: %s", header_path)
        return None

    try:
        with open(header_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        snap = ExecutionSnapshot(
            snapshot_id=data["snapshot_id"],
            session_id=data["session_id"],
            stage_id=data.get("stage_id", ""),
            strategy_name=data.get("strategy_name", ""),
            phase=data.get("phase", ""),
            state_summary=data.get("state_summary", {}),
            agent_configs=data.get("agent_configs", {}),
            timestamp=data.get("timestamp", 0),
            _state_path=os.path.join(_snapshot_dir(session_id), f"{snapshot_id}.json"),
        )
        return snap
    except Exception as e:
        logger.warning("ExecutionSnapshot: load failed: %s", e)
        return None


def list_execution_snapshots(session_id: str) -> List[Dict[str, Any]]:
    """List all snapshots for a session, newest first."""
    dstdir = _snapshot_dir(session_id)
    if not os.path.isdir(dstdir):
        return []

    results = []
    for fname in sorted(os.listdir(dstdir), reverse=True):
        if not fname.endswith(".header.json"):
            continue
        try:
            with open(os.path.join(dstdir, fname), "r", encoding="utf-8") as f:
                snap = json.load(f)
            snap["age_seconds"] = round(time.time() - snap.get("timestamp", 0), 1)
            results.append(snap)
        except Exception:
            continue
    return results


def compare_execution_snapshots(
    snapshot_a_id: str, snapshot_b_id: str, session_id: str
) -> Dict[str, Any]:
    """Compare two execution snapshots and return a diff.

    Returns:
        {
            "snapshot_a": {id, strategy, timestamp},
            "snapshot_b": {id, strategy, timestamp},
            "changes": {
                "tokens_used": {"before": N, "after": M, "delta": +X},
                "phase": {"before": "executing", "after": "done"},
                "artifacts": {"added": [...], "removed": [...], "changed": [...]},
                "classified_error": {"before": ..., "after": ...},
            },
            "strategy_effect": {
                "strategy": name,
                "phase_transition": "executing→done",
                "tokens_spent": N,
                "error_resolved": True/False,
            },
        }
    """
    snap_a = load_execution_snapshot(snapshot_a_id, session_id)
    snap_b = load_execution_snapshot(snapshot_b_id, session_id)

    def _meta(snap):
        if snap is None:
            return {}
        return {
            "id": snap.snapshot_id,
            "strategy": snap.strategy_name,
            "timestamp": snap.timestamp,
        }

    result: Dict[str, Any] = {
        "snapshot_a": _meta(snap_a),
        "snapshot_b": _meta(snap_b),
        "changes": {},
        "strategy_effect": {},
    }

    if snap_a is None or snap_b is None:
        result["error"] = "one or both snapshots failed to load"
        return result

    summary_a = snap_a.state_summary
    summary_b = snap_b.state_summary

    # Token change
    ta = summary_a.get("tokens_used", 0)
    tb = summary_b.get("tokens_used", 0)
    result["changes"]["tokens_used"] = {"before": ta, "after": tb, "delta": tb - ta}

    # Phase change
    result["changes"]["phase"] = {
        "before": summary_a.get("phase", ""),
        "after": summary_b.get("phase", ""),
    }

    # Error resolution
    err_a = summary_a.get("error", "")
    err_b = summary_b.get("error", "")
    result["changes"]["error"] = {
        "before": err_a,
        "after": err_b,
        "resolved": bool(err_a and not err_b),
    }

    # Classified error
    ce_a = summary_a.get("classified_error")
    ce_b = summary_b.get("classified_error")
    result["changes"]["classified_error"] = {"before": ce_a, "after": ce_b}

    # Healing diagnosis
    result["changes"]["healing_diagnosis"] = {
        "before": summary_a.get("healing_diagnosis", ""),
        "after": summary_b.get("healing_diagnosis", ""),
    }

    # Strategy effect summary
    result["strategy_effect"] = {
        "strategy": snap_b.strategy_name,
        "phase_transition": f"{summary_a.get('phase','')}→{summary_b.get('phase','')}",
        "tokens_spent": tb - ta,
        "error_resolved": bool(err_a and not err_b),
        "retry_count_change": summary_b.get("auto_retry_count", 0) - summary_a.get("auto_retry_count", 0),
    }

    return result


def snapshot_before_after(
    state: Dict[str, Any],
    strategy_name: str,
    *,
    session_id: str = "",
    stage_id: str = "",
) -> str:
    """Convenience: snapshot current state before a strategy executes. Returns snapshot_id."""
    sid = save_execution_snapshot(
        state, f"pre_{strategy_name}", session_id=session_id, stage_id=stage_id
    )
    return sid or ""


def snapshot_after_heal(
    state: Dict[str, Any],
    strategy_name: str,
    *,
    session_id: str = "",
    stage_id: str = "",
) -> Tuple[str, str]:
    """Save post-healing snapshot and return (pre_id, post_id) pair."""
    # Get pre snapshot ID from state
    pre_id = state.get("_last_snapshot_id", "")
    post_id = save_execution_snapshot(
        state, f"post_{strategy_name}", session_id=session_id, stage_id=stage_id
    ) or ""
    if pre_id and post_id:
        state["_last_snapshot_pair"] = [pre_id, post_id]
        logger.info(
            "[snapshot] healing pair: pre=%s post=%s strategy=%s",
            pre_id, post_id, strategy_name,
        )
    return pre_id, post_id


def _prune_session_snapshots(session_id: str, max_keep: int = 50) -> None:
    """Keep only the newest N snapshots per session."""
    dstdir = _snapshot_dir(session_id)
    if not os.path.isdir(dstdir):
        return
    headers = sorted(
        [f for f in os.listdir(dstdir) if f.endswith(".header.json")],
        reverse=True,
    )
    for old in headers[max_keep:]:
        prefix = old.replace(".header.json", "")
        for ext in (".header.json", ".json"):
            p = os.path.join(dstdir, f"{prefix}{ext}")
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass  # noqa: cleanup-best-effort


def get_reproducible_context_hash(state: Dict[str, Any]) -> str:
    """Generate a hash representing the reproducible execution context.

    This hash captures the environment in which a strategy was tried.
    Two runs with the same hash are reproducible peers for comparison.
    """
    context = {
        "session_id": state.get("session_id", ""),
        "stage_id": state.get("_last_error_stage", ""),
        "agent_type": state.get("_agent_type", ""),
        "iteration": state.get("iteration", 0),
        "tokens_used": state.get("tokens_used", 0),
        "artifact_keys": sorted(
            k for k in state
            if not k.startswith("_") and isinstance(state.get(k), dict) and state.get(k, {}).get("raw_output")
        ),
    }
    raw = json.dumps(context, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]

