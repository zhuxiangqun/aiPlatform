"""P2 session / multi-turn scoring — v0 (2–3) and v1 (5–8).

Honesty: engineering metrics only; accuracy_claim=false; not G2b.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MAX_TURNS_V0 = 3
MIN_TURNS_V0 = 2
MAX_TURNS_V1 = 8
MIN_TURNS_V1 = 5

PROFILES: Dict[str, Tuple[int, int]] = {
    "v0": (MIN_TURNS_V0, MAX_TURNS_V0),
    "v1": (MIN_TURNS_V1, MAX_TURNS_V1),
}


def resolve_profile(raw: Any = None, *, turns_n: Optional[int] = None) -> str:
    """Return v0|v1. Explicit profile wins; else infer from turn count."""
    p = str(raw or "").strip().lower()
    if p in PROFILES:
        return p
    if turns_n is not None and turns_n >= MIN_TURNS_V1:
        return "v1"
    return "v0"


def profile_bounds(profile: str) -> Tuple[int, int]:
    return PROFILES.get(profile, PROFILES["v0"])


def session_dimension(
    *,
    turns: Sequence[Mapping[str, Any]],
    turn_oks: Sequence[bool],
    session_id: str = "",
    profile: str = "v0",
) -> Dict[str, Any]:
    """Build session scoring block for v0 or v1."""
    prof = resolve_profile(profile)
    min_t, max_t = profile_bounds(prof)
    n = len(turns)
    oks = list(turn_oks)[:n]
    while len(oks) < n:
        oks.append(False)
    n_ok = sum(1 for x in oks if x)
    rate = round(n_ok / float(n), 4) if n else 0.0
    in_range = min_t <= n <= max_t
    return {
        "schema": f"eval.scoring.session.{prof}",
        "profile": prof,
        "accuracy_claim": False,
        "session_id": session_id or None,
        "turns_n": n,
        "turns_ok": n_ok,
        "turn_success_rate": rate,
        "session_pass": bool(in_range and n_ok == n and n > 0),
        "min_turns": min_t,
        "max_turns": max_t,
        "note": (
            f"multi-turn {prof} — {min_t}–{max_t} turns; turn_success_rate is engineering; "
            "not G2b accuracy / not full dialogue eval"
        ),
    }


def normalize_turns(raw: Any, *, profile: str = "v0") -> List[Dict[str, Any]]:
    """Accept list of turn dicts; clamp to profile max."""
    _, max_t = profile_bounds(resolve_profile(profile))
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
        if len(out) >= max_t:
            break
    return out


def _wire_session() -> Dict[str, Any]:
    return session_dimension(
        turns=[{"prompt": "a"}, {"prompt": "b"}],
        turn_oks=[True, True],
        session_id="wire",
        profile="v0",
    )
