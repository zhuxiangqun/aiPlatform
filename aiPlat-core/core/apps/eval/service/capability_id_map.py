"""Capability ID Map v1 — legacy ↔ canonical resolve (eval Case Pack P0).

Authority: docs/architecture/plans/CAPABILITY_ID_MAP_V1.md (Frozen).
canonical_id is the only key for coverage / Profile quotas.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence

MAP_SCHEMA = "eval.capability_id_map.v1"
MAP_VERSION = "1.0.0"

# Agent matrix A1–A13 (canonical).
CANONICAL_IDS = frozenset(
    {
        "task_completion",
        "planning",
        "tool_selection",
        "tool_args",
        "tool_result_use",
        "error_recovery",
        "safety",
        "multi_turn_memory",
        "long_context",
        "robustness",
        "efficiency",
        "observability",
        "clarification",
    }
)

# Frozen legacy → canonical (do not invent ids outside this table).
LEGACY_TO_CANONICAL = {
    "clarify_or_ask": "clarification",
    "error_recovery": "error_recovery",
    "multi_turn_memory": "multi_turn_memory",
    "skill_invoke": "task_completion",
    "http_chat_pull": "task_completion",
    "pi_export": "task_completion",
    "format_constraint": "task_completion",
    "consistency": "robustness",
    "multi_slot_context": "long_context",
    "long_chain": "planning",
}

# Plan §4.2.2 v1.1 measurable subset (Agent) — SIGNED v1_1_measurable_subset.
# Includes mock-tool / session / long-context fixture paths (claim still false).
V1_IN_SCOPE = frozenset(
    {
        "task_completion",
        "planning",
        "tool_selection",
        "tool_args",
        "tool_result_use",
        "error_recovery",
        "safety",
        "multi_turn_memory",
        "long_context",
        "robustness",
        "efficiency",
        "observability",
        "clarification",
    }
)

# Empty after v1.1 lift; kept as frozenset for callers / coverage reports.
V1_OUT_OF_SCOPE = frozenset()


class UnknownCapabilityId(ValueError):
    """Unknown legacy/canonical capability id (fail closed)."""


def resolve_capability_id(capability_id: str, *, fail_closed: bool = True) -> str:
    """Resolve one id to canonical.

    - Already canonical → return as-is.
    - Known legacy → mapped canonical.
    - Unknown → raise UnknownCapabilityId when fail_closed; else return stripped id.
    """
    raw = str(capability_id or "").strip()
    if not raw:
        if fail_closed:
            raise UnknownCapabilityId("empty capability_id")
        return ""
    key = raw.lower()
    if key in CANONICAL_IDS:
        return key
    mapped = LEGACY_TO_CANONICAL.get(key)
    if mapped:
        return mapped
    if fail_closed:
        raise UnknownCapabilityId(raw)
    return key


def resolve_capability_ids(
    ids: Sequence[str] | Iterable[str] | None,
    *,
    fail_closed: bool = True,
    dedupe: bool = True,
) -> List[str]:
    """Resolve many ids to canonical; preserve first-seen order when dedupe."""
    out: List[str] = []
    seen = set()
    for item in ids or ():
        cid = resolve_capability_id(str(item), fail_closed=fail_closed)
        if not cid:
            continue
        if dedupe and cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def is_v1_in_scope(capability_id: str) -> bool:
    """True if canonical (or resolvable) id is in signed v1 measurable subset."""
    try:
        cid = resolve_capability_id(capability_id, fail_closed=True)
    except UnknownCapabilityId:
        return False
    return cid in V1_IN_SCOPE


def capability_match_set(ids: Sequence[str] | Iterable[str] | None) -> set:
    """Canonical set for matching; unknown ids kept as lowercased tokens (migration)."""
    have: set = set()
    for item in ids or ():
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            have.add(resolve_capability_id(raw, fail_closed=True))
        except UnknownCapabilityId:
            have.add(raw.lower())
    return have
