#!/usr/bin/env python3
"""COMPLIANCE_PII_V0 report — heuristic leak gate (≠ privacy certification)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from app.scoring.compliance_pii import evaluate_compliance_cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    tasks_path = Path(args.tasks)
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    cases = list(payload.get("cases") or [])
    report: Dict[str, Any] = evaluate_compliance_cases(cases)
    report["tasks_ref"] = str(tasks_path)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "pass_rate": report["pass_rate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
