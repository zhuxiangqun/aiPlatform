#!/usr/bin/env python3
"""G2b accuracy closeout — adjudicated gold + model pass-rate (≠ κ).

Honesty:
- Inter-annotator κ is NOT accuracy.
- This script builds adjudicated gold (agree ∪ adjudicate disputes) and reports
  model pass-rate vs gold with Wilson 95% CI.
- Product-level ``accuracy_claim`` is **always false** (scheme A).
- ``scoped_accuracy_claim`` may be true only with ``--claim-ready`` AND an
  explicit product-owner attestation (``accept_accuracy_claim=true``).
- ``not_accuracy_certification`` stays true; refuse reason non-empty when product claim closed.
- Does not flip process_split_authorized / staging / security cert.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.scoring.g2b_accuracy import build_gold, wilson_ci


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
        raw = row.get("pass")
        if raw is None:
            raise SystemExit(f"unlabeled pass for {tid} in {path}")
        if not isinstance(raw, bool):
            raise SystemExit(f"pass must be bool for {tid} in {path}")
        out[tid] = raw
    return out


def _load_adjudication(path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("disputes") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise SystemExit(f"adjudication missing disputes[]: {path}")
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("task_id") or "").strip()
        if not tid:
            continue
        if "gold_pass" not in row or not isinstance(row.get("gold_pass"), bool):
            raise SystemExit(f"dispute {tid} missing bool gold_pass")
        out[tid] = row
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="G2b accuracy closeout (accuracy_claim=false by default)")
    ap.add_argument("--a", required=True, type=Path, help="annotator A worksheet")
    ap.add_argument("--b", required=True, type=Path, help="annotator B worksheet")
    ap.add_argument("--adjudication", required=True, type=Path, help="disputes adjudication JSON")
    ap.add_argument("--out-gold", type=Path, default=None, help="write adjudicated gold JSON")
    ap.add_argument("--out", type=Path, default=None, help="write accuracy aggregate JSON")
    ap.add_argument(
        "--claim-ready",
        action="store_true",
        help="request accuracy_claim=true (still refused without attestation file)",
    )
    ap.add_argument(
        "--attestation",
        type=Path,
        default=None,
        help="product-owner attestation JSON with accept_accuracy_claim=true",
    )
    args = ap.parse_args()

    la = _load_labels(args.a)
    lb = _load_labels(args.b)
    adj = _load_adjudication(args.adjudication)
    gold, agreed, disputed = build_gold(la, lb, adj)
    if len(gold) < 30:
        print(json.dumps({"error": "need_ge_30_gold", "n": len(gold)}), file=sys.stderr)
        return 2

    successes = sum(1 for v in gold.values() if v)
    n = len(gold)
    pass_rate = round(successes / float(n), 4)
    ci_lo, ci_hi = wilson_ci(successes, n)

    a_match = sum(1 for tid, g in gold.items() if la[tid] is g)
    b_match = sum(1 for tid, g in gold.items() if lb[tid] is g)

    # Scheme A: product accuracy_claim never opens; scoped is separate.
    scoped_claim = False
    claim_refuse = "产品级 accuracy 未认证；仅 G2b scoped"
    if args.claim_ready:
        if args.attestation and args.attestation.is_file():
            att = json.loads(args.attestation.read_text(encoding="utf-8"))
            if att.get("accept_accuracy_claim") is True and att.get("product_owner"):
                scoped_claim = True
            else:
                claim_refuse = "产品级 accuracy 未认证；attestation_incomplete"
        else:
            claim_refuse = "产品级 accuracy 未认证；attestation_missing"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    gold_payload = {
        "schema": "eval.g2b.adjudicated_gold.v1",
        "product_id": "evaluation",
        "environment": "local",
        "accuracy_claim": False,
        "scoped_accuracy_claim": False,
        "not_accuracy_certification": True,
        "n": n,
        "agreed_n": len(agreed),
        "disputed_n": len(disputed),
        "labels": [{"task_id": tid, "gold_pass": gold[tid]} for tid in sorted(gold)],
        "honesty": (
            "adjudicated gold for local model pass-rate only; "
            "κ ≠ accuracy; product accuracy_claim=false; scoped set only on aggregate"
        ),
        "recorded_at": stamp,
    }
    agg = {
        "schema": "eval.g2b.accuracy.v1",
        "product_id": "evaluation",
        "environment": "local",
        "accuracy_claim": False,
        "scoped_accuracy_claim": scoped_claim,
        "not_accuracy_certification": True,
        "metric": "model_pass_rate_vs_adjudicated_gold",
        "n": n,
        "pass_n": successes,
        "fail_n": n - successes,
        "pass_rate": pass_rate,
        "wilson_ci95": [ci_lo, ci_hi],
        "agreed_n": len(agreed),
        "disputed_n": len(disputed),
        "disputed_task_ids": disputed,
        "annotator_a_vs_gold": round(a_match / float(n), 4),
        "annotator_b_vs_gold": round(b_match / float(n), 4),
        "annotator_a": str(args.a),
        "annotator_b": str(args.b),
        "adjudication": str(args.adjudication),
        "claim_refuse_reason": claim_refuse,
        "honesty": (
            "model pass-rate vs adjudicated gold — not inter-annotator κ; "
            "not security cert; not process_split authorize; "
            "product accuracy_claim=false; scoped_accuracy_claim=true only with "
            "product-owner attestation (scheme A)"
        ),
        "recorded_at": stamp,
    }

    if args.out_gold:
        args.out_gold.parent.mkdir(parents=True, exist_ok=True)
        args.out_gold.write_text(
            json.dumps(gold_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(agg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "gate": "ok",
                "n": n,
                "pass_rate": pass_rate,
                "wilson_ci95": [ci_lo, ci_hi],
                "disputed_n": len(disputed),
                "accuracy_claim": False,
                "scoped_accuracy_claim": scoped_claim,
                "claim_refuse_reason": claim_refuse,
                "gold": str(args.out_gold) if args.out_gold else None,
                "evidence": str(args.out) if args.out else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
