"""P2 session / multi-turn v0 scoring (2–3 turns).

Honesty: engineering metrics only; accuracy_claim=false; not G2b.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


MAX_TURNS_V0 = 3
MIN_TURNS_V0 = 2


def session_dimension(
    *,
    turns: Sequence[Mapping[str, Any]],
    turn_oks: Sequence[bool],
    session_id: str = "",
) -> Dict[str, Any]:
    """Build ``eval.scoring.session.v0`` report block."""
    n = len(turns)
    oks = list(turn_oks)[:n]
    while len(oks) < n:
        oks.append(False)
    n_ok = sum(1 for x in oks if x)
    rate = round(n_ok / float(n), 4) if n else 0.0
    return {
        "schema": "eval.scoring.session.v0",
        "accuracy_claim": False,
        "session_id": session_id or None,
        "turns_n": n,
        "turns_ok": n_ok,
        "turn_success_rate": rate,
        "session_pass": bool(n >= MIN_TURNS_V0 and n_ok == n),
        "max_turns_v0": MAX_TURNS_V0,
        "note": (
            "multi-turn v0 — 2–3 turns only; turn_success_rate is engineering; "
            "not G2b accuracy / not full dialogue eval"
        ),
    }


def normalize_turns(raw: Any) -> List[Dict[str, Any]]:
    """Accept list of turn dicts; clamp to MAX_TURNS_V0."""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
        if len(out) >= MAX_TURNS_V0:
            break
    return out


def _wire_session() -> Dict[str, Any]:
    return session_dimension(
        turns=[{"prompt": "a"}, {"prompt": "b"}],
        turn_oks=[True, True],
        session_id="wire",
    )
