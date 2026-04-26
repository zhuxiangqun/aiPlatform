"""
Coverage gate utilities.

Purpose:
- Stabilize and freeze the evidence sampling contract:
  expected_tags MUST be executed (best-effort) when running browser evidence.
- Provide a deterministic "missing tags" failure reason (P0) to reduce flakiness noise.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        s = str(x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def evaluate_coverage(expected_tags: Iterable[str] | None, executed_tags: Iterable[str] | None) -> Tuple[bool, List[str]]:
    exp = unique_preserve_order(expected_tags or [])
    exe = set(unique_preserve_order(executed_tags or []))
    missing = [t for t in exp if t not in exe]
    return (len(missing) == 0), missing

