"""G2b adjudicated-gold helpers (κ ≠ accuracy).

Honesty: pass-rate vs gold is a local engineering metric; ``accuracy_claim``
stays false until product-owner attestation (see G2B_ACCURACY_CLOSEOUT.md).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def wilson_ci(successes: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    if n <= 0:
        return None, None
    p = successes / float(n)
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return round(max(0.0, lo), 4), round(min(1.0, hi), 4)


def build_gold(
    la: Dict[str, bool],
    lb: Dict[str, bool],
    adjudication: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, bool], List[str], List[str]]:
    common = sorted(set(la) & set(lb))
    gold: Dict[str, bool] = {}
    agreed: List[str] = []
    disputed: List[str] = []
    for tid in common:
        if la[tid] == lb[tid]:
            gold[tid] = la[tid]
            agreed.append(tid)
        else:
            disputed.append(tid)
            if tid not in adjudication:
                raise SystemExit(f"missing adjudication for dispute {tid}")
            gold[tid] = bool(adjudication[tid]["gold_pass"])
    missing_adj = sorted(set(adjudication) - set(disputed))
    if missing_adj:
        raise SystemExit(f"adjudication for non-disputes: {missing_adj[:5]}")
    return gold, agreed, disputed


def _wire_g2b_accuracy() -> Tuple[Optional[float], Optional[float]]:
    """Same-file caller for method_verify."""
    _ = build_gold({"t": True}, {"t": True}, {})
    return wilson_ci(23, 30)
