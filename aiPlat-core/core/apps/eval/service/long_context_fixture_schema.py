"""Long-context fixture schema v1 — T0 mechanical validate.

Authority: docs/architecture/plans/EVAL_AGENT_TOOL_SESSION_CONTRACTS_T0.md §3.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

FIXTURE_SCHEMA = "eval.long_context_fixture.v1"
_SLOT_KINDS = frozenset({"filler", "distractor", "conflict"})


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


def validate_long_context_fixture(fixture: Mapping[str, Any] | None) -> List[str]:
    """Return error codes; empty = pass.

    Args:
        fixture: fixture 参数。
    """
    if not isinstance(fixture, Mapping):
        return ["missing_field:long_context_fixture"]
    errors: List[str] = []
    if _nonempty_str(fixture.get("schema")) != FIXTURE_SCHEMA:
        errors.append("invalid_schema")

    tokens = fixture.get("context_tokens_est")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 100:
        errors.append("invalid_context_tokens_est")

    slots = fixture.get("noise_slots")
    if not isinstance(slots, (list, tuple)) or not slots:
        errors.append("empty_list:noise_slots")
    else:
        seen: set = set()
        for i, slot in enumerate(slots):
            if not isinstance(slot, Mapping):
                errors.append(f"invalid_noise_slot:{i}")
                continue
            sid = _nonempty_str(slot.get("slot_id"))
            if not sid:
                errors.append(f"missing_field:noise_slots[{i}].slot_id")
            elif sid in seen:
                errors.append(f"duplicate_noise_slot:{sid}")
            else:
                seen.add(sid)
            kind = _nonempty_str(slot.get("kind"))
            if kind not in _SLOT_KINDS:
                errors.append(f"invalid_noise_slots[{i}].kind")
            approx = slot.get("approx_tokens")
            if isinstance(approx, bool) or not isinstance(approx, int) or approx < 1:
                errors.append(f"invalid_noise_slots[{i}].approx_tokens")

    if not _str_list(fixture.get("must_retain_claims")):
        errors.append("empty_list:must_retain_claims")

    return _uniq(errors)


def validate_case_long_context_fields(case: Mapping[str, Any] | None) -> List[str]:
    """If case has long_context_fixture or capability long_context, validate fixture.

    Args:
        case: case 参数。
    """
    if not isinstance(case, Mapping):
        return ["missing_field:case"]
    fixture = case.get("long_context_fixture")
    caps = case.get("capabilities") or []
    cap_set = {str(c).strip().lower() for c in caps if str(c).strip()}
    needs = "long_context" in cap_set
    if fixture is None and not needs:
        return []
    if fixture is None and needs:
        return ["missing_field:long_context_fixture"]
    return validate_long_context_fixture(
        fixture if isinstance(fixture, Mapping) else None
    )


def _uniq(errors: Sequence[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out
