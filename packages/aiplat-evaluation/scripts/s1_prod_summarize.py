#!/usr/bin/env python3
"""Summarize S1 prod-model live drill → commit-safe aggregate (not security cert)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def summarize_s1_prod(drill: Dict[str, Any], *, prod_model: Optional[str] = None) -> Dict[str, Any]:
    model = prod_model or drill.get("prod_model") or drill.get("llm_model")
    return {
        "schema": "eval.s1.prod_model.aggregate.v1",
        "product_id": "evaluation",
        "environment": "local",
        "phase": "S1",
        "baseline_kind": "production_candidate",
        "prod_model": model,
        "accuracy_claim": False,
        "not_accuracy_certification": True,
        "not_security_certification": True,
        "process_split_authorized": False,
        "live_skill_tools": False,
        "suite_id": drill.get("suite_id"),
        "cases": drill.get("cases"),
        "asr": drill.get("asr"),
        "leak_rate": drill.get("leak_rate"),
        "false_refusal_rate": drill.get("false_refusal_rate"),
        "llm_ok_n": drill.get("llm_ok_n"),
        "llm_fail_n": drill.get("llm_fail_n"),
        "gate_ok": bool(drill.get("ok")),
        "source_drill": None,
        "honesty": (
            "S1 prod-candidate live_llm attack metrics — ASR/leak/false_refusal; "
            "accuracy_claim=false; ≠ security certification; ≠ staging"
        ),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize S1 prod-model drill → aggregate")
    ap.add_argument("--drill", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--prod-model", default="")
    args = ap.parse_args()
    drill = json.loads(args.drill.read_text(encoding="utf-8"))
    agg = summarize_s1_prod(drill, prod_model=args.prod_model or None)
    agg["source_drill"] = str(args.drill)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(agg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "gate": "ok" if agg["gate_ok"] else "fail",
                "prod_model": agg.get("prod_model"),
                "asr": agg.get("asr"),
                "leak_rate": agg.get("leak_rate"),
                "llm_ok_n": agg.get("llm_ok_n"),
                "out": str(args.out),
                "accuracy_claim": False,
                "not_security_certification": True,
            },
            ensure_ascii=False,
        )
    )
    return 0 if agg["gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
