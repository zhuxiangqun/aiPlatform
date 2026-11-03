"""Human preference / pairwise A/B v0 scoring.

Honesty: preference agreement is not accuracy; accuracy_claim=false.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def preference_dimension(
    *,
    pairs_n: int,
    preferred: Sequence[str],
    gold_preferred: Optional[Sequence[str]] = None,
    annotator_id: str = "",
) -> Dict[str, Any]:
    """Report block for solo preference labeling (no accuracy)."""
    prefs = [str(p).strip().lower() for p in preferred]
    valid = sum(1 for p in prefs if p in {"a", "b", "tie"})
    agree = None
    if gold_preferred is not None:
        gold = [str(g).strip().lower() for g in gold_preferred]
        n = min(len(prefs), len(gold))
        if n:
            agree = round(
                sum(1 for i in range(n) if prefs[i] == gold[i]) / float(n),
                4,
            )
    return {
        "schema": "eval.scoring.preference.v0",
        "accuracy_claim": False,
        "annotator_id": annotator_id or None,
        "pairs_n": pairs_n,
        "labeled_n": valid,
        "coverage": round(valid / float(pairs_n), 4) if pairs_n else 0.0,
        "agreement_vs_gold": agree,
        "note": (
            "human preference v0 — pairwise A/B; agreement≠accuracy; "
            "not G2b certification"
        ),
    }


def preference_agreement(
    a_prefs: Sequence[str],
    b_prefs: Sequence[str],
) -> Dict[str, Any]:
    """Inter-annotator agreement on preference labels (still not accuracy)."""
    n = min(len(a_prefs), len(b_prefs))
    pairs: List[Tuple[str, str]] = []
    for i in range(n):
        pa = str(a_prefs[i]).strip().lower()
        pb = str(b_prefs[i]).strip().lower()
        if pa in {"a", "b", "tie"} and pb in {"a", "b", "tie"}:
            pairs.append((pa, pb))
    if not pairs:
        return {
            "n": 0,
            "agreement": None,
            "accuracy_claim": False,
            "kappa_kind": "preference_pairwise",
        }
    agree_n = sum(1 for x, y in pairs if x == y)
    agreement = round(agree_n / float(len(pairs)), 4)
    # Simple multi-class κ (3 labels) via observed/chance
    labels = ("a", "b", "tie")
    pe = 0.0
    for lab in labels:
        pa = sum(1 for x, _ in pairs if x == lab) / float(len(pairs))
        pb = sum(1 for _, y in pairs if y == lab) / float(len(pairs))
        pe += pa * pb
    if pe >= 1.0:
        kappa = 1.0 if agreement == 1.0 else 0.0
    else:
        kappa = (agreement - pe) / (1.0 - pe)
    return {
        "n": len(pairs),
        "agreement": agreement,
        "preference_kappa": round(kappa, 4),
        "pe": round(pe, 4),
        "accuracy_claim": False,
        "kappa_kind": "preference_pairwise",
        "not_accuracy_certification": True,
    }


def load_preference_labels(data: Mapping[str, Any]) -> List[str]:
    labels = data.get("labels") if isinstance(data, dict) else None
    if not isinstance(labels, list):
        return []
    out: List[str] = []
    for row in labels:
        if isinstance(row, dict):
            out.append(str(row.get("preferred") or row.get("choice") or "").strip().lower())
    return out
