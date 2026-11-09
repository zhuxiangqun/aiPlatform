"""Session case field schema v1 — T0 mechanical validate.

Authority: docs/architecture/plans/EVAL_AGENT_TOOL_SESSION_CONTRACTS_T0.md §2.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

SESSION_SCHEMA = "eval.session_case.v1"


def _nonempty_str(v: Any) -> str:
    return str(v or "").strip()


def _str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, (list, tuple)):
        return [s for s in (_nonempty_str(x) for x in v) if s]
    return []


def validate_session_case_fields(case: Mapping[str, Any] | None) -> List[str]:
    """Validate session_group / turn_index / memory_probe on one case.

    Empty errors when none of the session fields are present (text-only case).
    """
    if not isinstance(case, Mapping):
        return ["missing_field:case"]
    errors: List[str] = []
    sg_raw = case.get("session_group")
    turn_raw = case.get("turn_index")
    probe = case.get("memory_probe")

    has_sg = sg_raw is not None and _nonempty_str(sg_raw) != ""
    has_turn = turn_raw is not None
    has_probe = probe is not None

    if not has_sg and not has_turn and not has_probe:
        return []

    if has_turn and not has_sg:
        errors.append("turn_index_requires_session_group")
    if has_probe and not has_sg:
        errors.append("memory_probe_requires_session_group")

    if has_sg and not _nonempty_str(sg_raw):
        errors.append("empty_session_group")

    if has_turn:
        if isinstance(turn_raw, bool) or not isinstance(turn_raw, int):
            errors.append("invalid_turn_index")
        elif turn_raw < 0:
            errors.append("invalid_turn_index")

    if has_probe:
        if not isinstance(probe, Mapping):
            errors.append("invalid_memory_probe")
        else:
            if not _nonempty_str(probe.get("planted_fact")):
                errors.append("missing_field:memory_probe.planted_fact")
            ask = probe.get("ask_after_turns")
            if isinstance(ask, bool) or not isinstance(ask, int) or ask < 1:
                errors.append("invalid_memory_probe.ask_after_turns")
            if not _str_list(probe.get("must_recall")):
                errors.append("empty_list:memory_probe.must_recall")

    return _uniq(errors)


def validate_session_group_unique_turns(
    cases: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Volume-level: turn_index unique within each session_group."""
    by_group: Dict[str, List[int]] = {}
    errors: List[str] = []
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        sg = _nonempty_str(case.get("session_group"))
        if not sg:
            continue
        turn = case.get("turn_index")
        if turn is None:
            errors.append(f"session_group_missing_turn:{sg}")
            continue
        if isinstance(turn, bool) or not isinstance(turn, int):
            continue
        by_group.setdefault(sg, []).append(turn)
    for sg, turns in by_group.items():
        if len(turns) != len(set(turns)):
            errors.append(f"duplicate_turn_index:{sg}")
    return _uniq(errors)


def _uniq(errors: Sequence[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out
