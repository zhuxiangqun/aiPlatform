#!/usr/bin/env python3
"""Inter-annotator Cohen's κ for G2b worksheets.

accuracy_claim stays false. Does not unlock G2b closeout / external gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def cohen_kappa_binary(pairs: List[Tuple[bool, bool]]) -> Dict[str, Any]:
    n = len(pairs)
    if n == 0:
        return {
            "n": 0,
            "agreement": None,
            "inter_annotator_kappa": None,
            "pe": None,
        }
    agree_n = sum(1 for a, b in pairs if a is b)
    agreement = agree_n / float(n)
    p_a_true = sum(1 for a, _ in pairs if a) / float(n)
    p_b_true = sum(1 for _, b in pairs if b) / float(n)
    pe = p_a_true * p_b_true + (1.0 - p_a_true) * (1.0 - p_b_true)
    if pe >= 1.0:
        kappa = 1.0 if agreement == 1.0 else 0.0
    else:
        kappa = (agreement - pe) / (1.0 - pe)
    return {
        "n": n,
        "agreement": round(agreement, 4),
        "inter_annotator_kappa": round(kappa, 4),
        "pe": round(pe, 4),
        "p_a_true": round(p_a_true, 4),
        "p_b_true": round(p_b_true, 4),
    }


def _load_labels(path: Path) -> Dict[str, bool]:
    data = json.loads(path.read_text(encoding="utf-8"))
    labels = data.get("labels") if isinstance(data, dict) else None
    if not isinstance(labels, list):
        raise SystemExit(f"worksheet missing labels[]: {path}")
    out: Dict[str, bool] = {}
    for row in labels:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("task_id") or row.get("id") or "").strip()
        if not tid:
            continue
        if "pass" not in row:
            raise SystemExit(f"label missing pass for {tid} in {path}")
        raw = row.get("pass")
        if raw is None:
            raise SystemExit(
                f"label pass is null (unlabeled) for {tid} in {path} — set true|false"
            )
        if not isinstance(raw, bool):
            raise SystemExit(f"label pass must be bool for {tid} in {path}, got {type(raw).__name__}")
        out[tid] = raw
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="G2b inter-annotator κ (accuracy_claim=false)")
    ap.add_argument("--a", required=True, type=Path, help="annotator A worksheet JSON")
    ap.add_argument("--b", required=True, type=Path, help="annotator B worksheet JSON")
    ap.add_argument("--tasks", type=Path, default=None, help="optional task pack to require ≥30 ids")
    ap.add_argument("--out", type=Path, default=None, help="evidence JSON path")
    args = ap.parse_args()

    la = _load_labels(args.a)
    lb = _load_labels(args.b)
    common = sorted(set(la) & set(lb))
    if args.tasks and args.tasks.is_file():
        pack = json.loads(args.tasks.read_text(encoding="utf-8"))
        need = [str(t.get("id")) for t in (pack.get("tasks") or []) if isinstance(t, dict)]
        missing = [i for i in need if i not in common]
        if len(need) < 30:
            print(json.dumps({"error": "task_pack_lt_30", "n": len(need)}), file=sys.stderr)
            return 2
        if missing:
            print(
                json.dumps({"error": "incomplete_pair", "missing_n": len(missing), "sample": missing[:5]}),
                file=sys.stderr,
            )
            return 2
        common = need

    if len(common) < 30:
        print(
            json.dumps({"error": "need_ge_30_paired", "paired": len(common)}),
            file=sys.stderr,
        )
        return 2

    pairs = [(la[i], lb[i]) for i in common]
    stats = cohen_kappa_binary(pairs)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "schema": "eval.g2b.kappa.v0",
        "product_id": "evaluation",
        "environment": "local",
        "accuracy_claim": False,
        "not_accuracy_certification": True,
        "kappa_kind": "inter_annotator",
        "annotator_a": str(args.a),
        "annotator_b": str(args.b),
        "task_ids": common,
        **stats,
        "honesty": (
            "inter-annotator κ for G2b prep only — not accuracy certification; "
            "not external gate; not process_split authorize"
        ),
        "recorded_at": stamp,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(json.dumps({
        "gate": "ok",
        "n": stats["n"],
        "agreement": stats["agreement"],
        "inter_annotator_kappa": stats["inter_annotator_kappa"],
        "accuracy_claim": False,
        "evidence": str(args.out) if args.out else None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
