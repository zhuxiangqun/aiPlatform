#!/usr/bin/env python3
"""Aggregate filled P2-0 human calibration CSVs → evidence JSON.

Honesty: accuracy_claim stays false; disagreement rate ≠ accuracy certification.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping


VALID = {"AGREE", "DISAGREE", "UNSURE"}


def _norm(raw: str) -> str:
    s = (raw or "").strip().upper()
    if s in VALID:
        return s
    raise SystemExit(f"bad recheck value: {raw!r} (want AGREE|DISAGREE|UNSURE)")


def _load_csv(path: Path) -> List[Dict[str, str]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    if not rows:
        raise SystemExit(f"empty csv: {path}")
    for r in rows:
        if not str(r.get("recheck") or "").strip():
            raise SystemExit(f"unlabeled recheck in {path.name} item={r.get('item_id')}")
        r["recheck"] = _norm(str(r.get("recheck") or ""))
    return rows


def _track_stats(rows: List[Mapping[str, str]]) -> Dict[str, Any]:
    c = Counter(str(r["recheck"]) for r in rows)
    n = len(rows)
    disagree = c.get("DISAGREE", 0)
    return {
        "n": n,
        "agree_n": c.get("AGREE", 0),
        "disagree_n": disagree,
        "unsure_n": c.get("UNSURE", 0),
        "disagree_rate": round(disagree / float(n), 4) if n else None,
        "counts": dict(c),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, required=True, help="calibration pack dir with CSVs")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    tracks = {
        "g2b": _load_csv(args.pack / "calibration_g2b.csv"),
        "arena": _load_csv(args.pack / "calibration_arena.csv"),
        "preference": _load_csv(args.pack / "calibration_preference.csv"),
    }
    per = {k: _track_stats(v) for k, v in tracks.items()}
    total_n = sum(v["n"] for v in per.values())
    total_disagree = sum(v["disagree_n"] for v in per.values())

    payload = {
        "schema": "eval.human_calibration.v0",
        "accuracy_claim": False,
        "not_accuracy_certification": True,
        "product_id": "evaluation",
        "environment": "local",
        "pack": str(args.pack),
        "tracks": per,
        "overall": {
            "n": total_n,
            "disagree_n": total_disagree,
            "disagree_rate": round(total_disagree / float(total_n), 4) if total_n else None,
        },
        "retunes_composite": False,
        "replaces_length_smoke": False,
        "honesty": (
            "human recheck disagreement rates only; ≠ accuracy claim; "
            "≠ composite reweight; ≠ process_split"
        ),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "overall": payload["overall"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
