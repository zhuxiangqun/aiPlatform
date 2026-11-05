#!/usr/bin/env python3
"""Build P2-0 human calibration sample packs (accuracy_claim=false).

Honesty: sampling for human recheck only — does not retune composite or flip claims.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sample_g2b(rng: random.Random, n_each: int = 10) -> List[Dict[str, Any]]:
    gold = _load(ROOT / "docs/a3/evidence/g2b_adjudicated_gold.v1.json")
    labels = {str(r["task_id"]): bool(r["gold_pass"]) for r in gold["labels"]}
    fac = _load(ROOT / "docs/a3/human_pack/20261105T132500Z-n100/g2b_facilitator.json")
    by_id = {str(t["task_id"]): t for t in fac.get("tasks") or []}
    pos = [tid for tid, g in labels.items() if g]
    neg = [tid for tid, g in labels.items() if not g]
    rng.shuffle(pos)
    rng.shuffle(neg)
    picked = pos[:n_each] + neg[:n_each]
    rows: List[Dict[str, Any]] = []
    for tid in picked:
        t = by_id.get(tid) or {}
        rows.append(
            {
                "track": "g2b",
                "item_id": tid,
                "prompt": t.get("prompt") or "",
                "rubric": t.get("rubric") or "",
                "model_output": t.get("model_output") or "",
                "original_conclusion": "PASS" if labels[tid] else "FAIL",
                "context": "gold_pass from adjudicated G2b gold",
                "recheck": "",
                "notes": "",
            }
        )
    return rows


def _length_winner(a: str, b: str) -> str:
    la, lb = len(a or ""), len(b or "")
    if la == lb:
        return "tie"
    return "model_a" if la > lb else "model_b"


def _sample_arena(rng: random.Random, n: int = 20) -> List[Dict[str, Any]]:
    pairs = {
        str(p["pair_id"]): p
        for p in _load(ROOT / "docs/a3/arena_blind_pairs.pilot_20261105.json")["pairs"]
    }
    gold_rows = _load(ROOT / "docs/a3/evidence/arena_blind_adjudicated_gold.v1.json")["pairs"]
    disagree: List[Mapping[str, Any]] = []
    agree: List[Mapping[str, Any]] = []
    for g in gold_rows:
        pid = str(g["pair_id"])
        p = pairs[pid]
        lw = _length_winner(str(p.get("response_a") or ""), str(p.get("response_b") or ""))
        gw = str(g.get("winner_slot") or "tie")
        bucket = disagree if lw != gw else agree
        bucket.append({**g, "_length": lw, "_pair": p})
    rng.shuffle(disagree)
    rng.shuffle(agree)
    picked = (disagree + agree)[:n]
    rows: List[Dict[str, Any]] = []
    for g in picked:
        p = g["_pair"]
        rows.append(
            {
                "track": "arena",
                "item_id": g["pair_id"],
                "prompt": p.get("prompt") or "",
                "left": p.get("response_a") or "",
                "right": p.get("response_b") or "",
                "length_winner_slot": g["_length"],
                "blind_gold_slot": g.get("winner_slot") or "",
                "blind_gold_label": g.get("gold_label") or "",
                "original_conclusion": (
                    "LENGTH_EQ_BLIND"
                    if g["_length"] == g.get("winner_slot")
                    else "LENGTH_NE_BLIND"
                ),
                "context": "recheck whether blind gold is preferable to length heuristic",
                "recheck": "",
                "notes": "",
            }
        )
    return rows


def _sample_preference(rng: random.Random, n: int = 20) -> List[Dict[str, Any]]:
    sheet = _load(ROOT / "docs/a3/human_pack/20261103T130302Z/pref_annotator_a.json")
    labels = list(sheet.get("labels") or [])
    rng.shuffle(labels)
    rows: List[Dict[str, Any]] = []
    for r in labels[:n]:
        rows.append(
            {
                "track": "preference",
                "item_id": r.get("pair_id") or "",
                "prompt": r.get("prompt") or "",
                "option_a": r.get("a") or "",
                "option_b": r.get("b") or "",
                "original_conclusion": str(r.get("preferred") or "").lower(),
                "context": "annotator_a preferred from 20261103T130302Z pack",
                "recheck": "",
                "notes": "",
            }
        )
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise SystemExit(f"no rows for {path}")
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "docs/a3/human_pack/calibration")
    ap.add_argument("--seed", type=int, default=20261106)
    args = ap.parse_args(list(argv) if argv is not None else None)

    rng = random.Random(int(args.seed))
    stamp = _stamp()
    dest = args.out / stamp
    dest.mkdir(parents=True, exist_ok=True)

    g2b = _sample_g2b(rng)
    arena = _sample_arena(rng)
    pref = _sample_preference(rng)
    _write_csv(dest / "calibration_g2b.csv", g2b)
    _write_csv(dest / "calibration_arena.csv", arena)
    _write_csv(dest / "calibration_preference.csv", pref)

    meta = {
        "schema": "eval.human_calibration.pack.v0",
        "accuracy_claim": False,
        "stamp": stamp,
        "seed": int(args.seed),
        "counts": {"g2b": len(g2b), "arena": len(arena), "preference": len(pref)},
        "protocol": "docs/a3/CALIBRATION_V0.md",
        "recheck_values": ["AGREE", "DISAGREE", "UNSURE"],
        "honesty": (
            "human recheck pack only; does not retune composite; "
            "accuracy_claim=false; length smoke not replaced"
        ),
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (dest / "SEND_CN.md").write_text(
        """# P2-0 人工校准发卷

每轨 CSV 的 `recheck` 只填：`AGREE` / `DISAGREE` / `UNSURE`。

| 文件 | 建议复核人 |
|---|---|
| calibration_g2b.csv | 朱鸿林 |
| calibration_arena.csv | 朱莹 |
| calibration_preference.csv | 朱向群或第三人 |

填完交回工程跑 `calibration_aggregate.py`。`accuracy_claim` 保持 false。
""",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "dest": str(dest), **meta["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
