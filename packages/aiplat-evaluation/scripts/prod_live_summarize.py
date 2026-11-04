#!/usr/bin/env python3
"""Summarize a prod-live drill JSON into a commit-safe aggregate (accuracy_claim=false).

Does not flip process_split_authorized. Drills stay gitignored; aggregate may be committed.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _f(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def summarize_prod_live(drill: Dict[str, Any]) -> Dict[str, Any]:
    runs = drill.get("runs") if isinstance(drill.get("runs"), list) else []
    live = [r for r in runs if str(r.get("mode_label", "")).startswith("live_")]
    lats: List[float] = []
    toks_in: List[float] = []
    toks_out: List[float] = []
    costs: List[float] = []
    ok_n = 0
    fail_n = 0
    timeout_n = 0
    for r in live:
        audit = r.get("audit") if isinstance(r.get("audit"), dict) else {}
        lat = _f(audit.get("latency_ms"))
        if lat is not None:
            lats.append(lat)
        ti = _f(audit.get("tokens_in"))
        to = _f(audit.get("tokens_out"))
        if ti is not None:
            toks_in.append(ti)
        if to is not None:
            toks_out.append(to)
        c = _f(audit.get("cost_estimate"))
        if c is not None:
            costs.append(c)
        status = str(r.get("status") or "")
        detail = str(audit.get("detail") or r.get("detail") or "").lower()
        if status == "succeeded" and r.get("ok"):
            ok_n += 1
        elif "timeout" in detail or status == "timeout":
            timeout_n += 1
            fail_n += 1
        else:
            fail_n += 1

    def pct(vals: List[float], q: float) -> Optional[float]:
        if not vals:
            return None
        s = sorted(vals)
        idx = min(len(s) - 1, max(0, int(round((len(s) - 1) * q))))
        return round(s[idx], 2)

    model = drill.get("prod_model") or drill.get("provider", {}).get("model")
    return {
        "schema": "eval.prod_live.aggregate.v1",
        "product_id": "evaluation",
        "environment": "local",
        "accuracy_claim": False,
        "not_accuracy_certification": True,
        "process_split_authorized": False,
        "baseline_kind": "production_candidate",
        "prod_model": model,
        "provider": drill.get("provider"),
        "task_count": drill.get("task_count"),
        "repeats": drill.get("repeats"),
        "live_attempt_n": len(live),
        "llm_ok_n": drill.get("llm_ok_n"),
        "gate_ok": bool(drill.get("gate_ok")),
        "succeeded_n": ok_n,
        "fail_n": fail_n,
        "timeout_n": timeout_n,
        "latency_ms": {
            "n": len(lats),
            "p50": pct(lats, 0.50),
            "p95": pct(lats, 0.95),
            "mean": round(statistics.fmean(lats), 2) if lats else None,
        },
        "tokens_out": {
            "n": len(toks_out),
            "mean": round(statistics.fmean(toks_out), 2) if toks_out else None,
            "sum": round(sum(toks_out), 2) if toks_out else None,
        },
        "tokens_in": {
            "n": len(toks_in),
            "mean": round(statistics.fmean(toks_in), 2) if toks_in else None,
            "sum": round(sum(toks_in), 2) if toks_in else None,
        },
        "total_cost_estimate": drill.get("total_cost_estimate"),
        "cost_ok": drill.get("cost_ok"),
        "source_drill": None,
        "compare_note": (
            "Compare against prior 3B smoke / 7b×1 drills locally; "
            "this aggregate is engineering baseline only"
        ),
        "honesty": (
            "production-candidate live aggregate — latency/cost/fail; "
            "accuracy_claim=false; ≠ G2b accuracy; ≠ staging; ≠ security cert"
        ),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize prod-live drill → aggregate JSON")
    ap.add_argument("--drill", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    drill = json.loads(args.drill.read_text(encoding="utf-8"))
    agg = summarize_prod_live(drill)
    agg["source_drill"] = str(args.drill)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(agg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "gate": "ok" if agg.get("gate_ok") else "fail",
                "prod_model": agg.get("prod_model"),
                "live_attempt_n": agg.get("live_attempt_n"),
                "llm_ok_n": agg.get("llm_ok_n"),
                "latency_p50": (agg.get("latency_ms") or {}).get("p50"),
                "latency_p95": (agg.get("latency_ms") or {}).get("p95"),
                "out": str(args.out),
                "accuracy_claim": False,
            },
            ensure_ascii=False,
        )
    )
    return 0 if agg.get("gate_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
