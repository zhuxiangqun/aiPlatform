#!/usr/bin/env python3
"""Generate Arena blind annotator sheets (A/B/Tie) — P1b scaffold.

Honesty: strips model names; randomizes left/right; accuracy_claim=false;
length_heuristic winner must never appear on annotator sheets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCHEMA_ANNOTATOR = "eval.arena.blind.worksheet.v0"
SCHEMA_FACILITATOR = "eval.arena.blind.facilitator.v0"
JUDGE_VERSION = "arena.blind.v1"


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _swap_side(pair_id: str, salt: str) -> bool:
    """Deterministic swap: True → put response_b on Left."""
    digest = hashlib.sha256(f"{salt}:{pair_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 2 == 1


def build_facilitator_rows(
    pairs: Sequence[Mapping[str, Any]],
    *,
    salt: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in pairs:
        pid = str(raw.get("pair_id") or "").strip()
        if not pid:
            continue
        swap = _swap_side(pid, salt)
        left_is = "b" if swap else "a"
        right_is = "a" if swap else "b"
        a = str(raw.get("response_a") or "")
        b = str(raw.get("response_b") or "")
        left = b if swap else a
        right = a if swap else b
        rows.append(
            {
                "pair_id": pid,
                "prompt": raw.get("prompt"),
                "left": left,
                "right": right,
                "left_is": left_is,
                "right_is": right_is,
                "model_a": raw.get("model_a"),
                "model_b": raw.get("model_b"),
                "swap": swap,
            }
        )
    return rows


def build_annotator_sheet(
    facilitator_rows: Sequence[Dict[str, Any]],
    *,
    annotator_id: str,
) -> Dict[str, Any]:
    labels: List[Dict[str, Any]] = []
    for row in facilitator_rows:
        labels.append(
            {
                "pair_id": row["pair_id"],
                "prompt": row.get("prompt"),
                "left": row.get("left"),
                "right": row.get("right"),
                # Annotator MUST set A|B|Tie (null = unlabeled).
                "label": None,
                "notes": "",
            }
        )
    return {
        "schema": SCHEMA_ANNOTATOR,
        "accuracy_claim": False,
        "judge_version": JUDGE_VERSION,
        "annotator_id": annotator_id,
        "blind": True,
        "instructions": (
            "For each pair_id: read prompt + Left + Right. "
            "Set label to A (prefer Left), B (prefer Right), or Tie. "
            "Do not estimate length winners. Do not share labels with other annotators. "
            "Follow ARENA_BLIND_RUBRIC_V1."
        ),
        "labels": labels,
    }


def build_facilitator_pack(
    facilitator_rows: Sequence[Dict[str, Any]],
    *,
    salt: str,
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA_FACILITATOR,
        "accuracy_claim": False,
        "judge_version": JUDGE_VERSION,
        "not_for_annotators": True,
        "salt": salt,
        "instructions": (
            "Coordinator only. Never send this file to annotators. "
            "left_is/right_is map sheet sides back to response_a/response_b. "
            "Length heuristic winner must not be shown to annotators."
        ),
        "pairs": list(facilitator_rows),
    }


def write_pack(
    pairs_path: Path,
    out_root: Path,
    *,
    annotators: Sequence[str],
    salt: str,
) -> Path:
    data = _load(pairs_path)
    pairs = data.get("pairs") if isinstance(data.get("pairs"), list) else []
    rows = build_facilitator_rows(pairs, salt=salt)
    stamp = _stamp()
    dest = out_root / stamp
    dest.mkdir(parents=True, exist_ok=True)
    fac = build_facilitator_pack(rows, salt=salt)
    (dest / "facilitator.json").write_text(
        json.dumps(fac, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for aid in annotators:
        sheet = build_annotator_sheet(rows, annotator_id=aid)
        name = f"annotator_{aid}.json"
        (dest / name).write_text(
            json.dumps(sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    meta = {
        "schema": "eval.arena.blind.pack.meta.v0",
        "accuracy_claim": False,
        "judge_version": JUDGE_VERSION,
        "stamp": stamp,
        "pairs_source": str(pairs_path),
        "pair_count": len(rows),
        "annotators": list(annotators),
        "rubric": "docs/a3/ARENA_BLIND_RUBRIC_V1.md",
        "pilot": "docs/a3/ARENA_BLIND_PILOT.md",
        "note": "Scaffold only; pilot complete only with ≥30 real pairs × ≥2 annotators.",
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pairs",
        type=Path,
        default=Path("docs/a3/arena_blind_pairs.v0.json"),
        help="Pairs JSON (facilitator source)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("docs/a3/human_pack/arena_blind"),
        help="Output root for stamped pack dirs",
    )
    ap.add_argument(
        "--annotators",
        type=str,
        default="r1,r2",
        help="Comma-separated annotator ids",
    )
    ap.add_argument(
        "--salt",
        type=str,
        default="arena.blind.v1",
        help="Deterministic left/right shuffle salt",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    aids = [a.strip() for a in str(args.annotators).split(",") if a.strip()]
    if len(aids) < 2:
        raise SystemExit("need at least two annotator ids")
    dest = write_pack(args.pairs, args.out, annotators=aids, salt=str(args.salt))
    print(f"OK wrote {dest} pairs={len(list(dest.glob('annotator_*.json')))} annotators")
    return 0


def _wire_pack() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Same-file caller for method_verify."""
    rows = build_facilitator_rows(
        [
            {
                "pair_id": "arena-x",
                "prompt": "p",
                "response_a": "aa",
                "response_b": "bbb",
                "model_a": "m1",
                "model_b": "m2",
            }
        ],
        salt="t",
    )
    return build_facilitator_pack(rows, salt="t"), build_annotator_sheet(
        rows, annotator_id="r1"
    )


if __name__ == "__main__":
    raise SystemExit(main())
