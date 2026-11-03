#!/usr/bin/env python3
"""Preference v0 report — pairwise agreement (accuracy_claim=false)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scoring.preference import (  # noqa: E402
    load_preference_labels,
    preference_agreement,
    preference_dimension,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    pairs = json.loads(args.pairs.read_text(encoding="utf-8")).get("pairs") or []
    assert len(pairs) >= 30, f"need >=30 pairs, got {len(pairs)}"
    a_data = json.loads(args.a.read_text(encoding="utf-8"))
    a_prefs = load_preference_labels(a_data)
    assert len(a_prefs) >= 30, "annotator A needs >=30 labels"

    dim_a = preference_dimension(
        pairs_n=len(pairs),
        preferred=a_prefs,
        annotator_id=str(a_data.get("annotator_id") or "A"),
    )
    inter = None
    dim_b = None
    if args.b:
        b_data = json.loads(args.b.read_text(encoding="utf-8"))
        b_prefs = load_preference_labels(b_data)
        assert len(b_prefs) >= 30, "annotator B needs >=30 labels"
        dim_b = preference_dimension(
            pairs_n=len(pairs),
            preferred=b_prefs,
            annotator_id=str(b_data.get("annotator_id") or "B"),
        )
        inter = preference_agreement(a_prefs, b_prefs)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "schema": "eval.preference.v0.report",
        "product_id": "evaluation",
        "environment": "local",
        "accuracy_claim": False,
        "not_accuracy_certification": True,
        "pairs_n": len(pairs),
        "annotator_a": dim_a,
        "annotator_b": dim_b,
        "inter_annotator": inter,
        "honesty": (
            "human preference v0 — pairwise A/B; agreement/κ ≠ accuracy; "
            "not G2b closeout; not authorize"
        ),
        "recorded_at": stamp,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "gate": "ok",
                "pairs_n": len(pairs),
                "coverage_a": dim_a["coverage"],
                "inter_agreement": (inter or {}).get("agreement"),
                "accuracy_claim": False,
                "evidence": str(args.out) if args.out else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
