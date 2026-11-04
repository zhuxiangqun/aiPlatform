#!/usr/bin/env python3
"""Run candidate model on G2b task pack → flat model_outputs.json.

Honesty:
- Facilitator helper only — does not label pass/fail.
- accuracy_claim stays false; dual-human A/B still required for G2b closeout.
- Uses Eval Worker LLM client (independent provider; never Central :8000).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.llm.client import complete_text, llm_enabled


def main() -> int:
    """CLI — delegates to ``g2b_run_model_outputs`` (registry / wiring symbol)."""
    return g2b_run_model_outputs()


def g2b_run_model_outputs(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="G2b facilitator model_outputs runner")
    ap.add_argument(
        "--tasks",
        type=Path,
        default=Path("docs/a3/g2b_tasks.v0.json"),
        help="task pack JSON",
    )
    ap.add_argument(
        "--out",
        type=Path,
        required=True,
        help="flat model_outputs.json path",
    )
    ap.add_argument(
        "--model",
        default="",
        help="override AIPLAT_EVAL_LLM_MODEL",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="keep existing non-empty outputs and only fill missing ids",
    )
    ap.add_argument("--limit", type=int, default=0, help="optional cap for smoke")
    args = ap.parse_args(argv)

    if not llm_enabled():
        print(
            json.dumps(
                {
                    "error": "llm_disabled",
                    "hint": "export AIPLAT_EVAL_LLM=1 AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 "
                    "AIPLAT_EVAL_LLM_MODEL=qwen2.5-coder:7b",
                }
            ),
            file=sys.stderr,
        )
        return 2

    pack = json.loads(args.tasks.read_text(encoding="utf-8"))
    task_rows = pack.get("tasks") if isinstance(pack, dict) else None
    if not isinstance(task_rows, list) or not task_rows:
        raise SystemExit(f"bad task pack: {args.tasks}")

    outputs: Dict[str, str] = {}
    if args.resume and args.out.is_file():
        prev = json.loads(args.out.read_text(encoding="utf-8"))
        if isinstance(prev, dict):
            outputs = {str(k): str(v) for k, v in prev.items() if str(v).strip()}

    failures = 0
    ran = 0
    for t in task_rows:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        prompt = str(t.get("prompt") or "").strip()
        if not tid or not prompt:
            continue
        if args.limit and ran >= args.limit:
            break
        if args.resume and outputs.get(tid, "").strip():
            continue
        r = complete_text(
            prompt,
            job_id=f"g2b-model-outputs:{tid}",
            runner_id="g2b_run_model_outputs",
            purpose="g2b_facilitator",
            model=args.model or None,
        )
        ran += 1
        if not r.get("ok"):
            failures += 1
            outputs[tid] = ""
            print(json.dumps({"task_id": tid, "ok": False, "audit": r.get("audit")}), flush=True)
            continue
        text = str(r.get("text") or "").strip()
        outputs[tid] = text
        print(json.dumps({"task_id": tid, "ok": True, "chars": len(text)}), flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(outputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary: Dict[str, Any] = {
        "schema": "eval.g2b.model_outputs_run.v1",
        "accuracy_claim": False,
        "n_tasks": len(task_rows),
        "n_filled": sum(1 for v in outputs.values() if str(v).strip()),
        "n_empty": sum(1 for v in outputs.values() if not str(v).strip()),
        "failures": failures,
        "out": str(args.out),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "honesty": "facilitator outputs only; dual-human A/B labels still required for n=100 closeout",
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if failures == 0 and summary["n_empty"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
