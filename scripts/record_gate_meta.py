#!/usr/bin/env python3
"""Append gate meta-eval events (skip / appeal) for duty-board calibration.

Usage:
  python3 scripts/record_gate_meta.py --skip --env SKIP_PHYSICAL_GATES
  python3 scripts/record_gate_meta.py --appeal --code banned_basename --owner alice \\
      --note "scheduler.py is a legitimate domain name"
  python3 scripts/record_gate_meta.py --summary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ensure_path() -> None:
    core = str(ROOT / "aiPlat-core")
    if core not in sys.path:
        sys.path.insert(0, core)


def main() -> int:
    ap = argparse.ArgumentParser(description="Record gate meta-eval skip/appeal events")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--skip", action="store_true", help="record SKIP_* bypass")
    g.add_argument("--appeal", action="store_true", help="record false-positive appeal")
    g.add_argument("--summary", action="store_true", help="print gate_meta summary JSON")
    ap.add_argument("--env", default="SKIP_PHYSICAL_GATES", help="skip env name")
    ap.add_argument("--gate", default="physical", help="gate id")
    ap.add_argument("--source", default="cli", help="event source")
    ap.add_argument("--code", default="", help="finding code (appeal)")
    ap.add_argument("--owner", default="", help="appeal owner")
    ap.add_argument("--note", default="", help="optional note")
    args = ap.parse_args()

    _ensure_path()
    from core.harness.meta.gate_meta_eval import (
        assess_gate_meta,
        record_gate_appeal,
        record_gate_skip,
    )

    if args.summary:
        print(json.dumps(assess_gate_meta(), ensure_ascii=False, indent=2))
        return 0
    if args.skip:
        path = record_gate_skip(
            env=args.env,
            gate=args.gate,
            source=args.source,
            note=args.note,
        )
        print(path or "persist skipped")
        return 0 if path else 1
    path = record_gate_appeal(
        code=args.code,
        owner=args.owner,
        note=args.note,
        gate=args.gate,
        source=args.source,
    )
    print(path or "persist skipped (need --code and --owner)")
    return 0 if path else 1


if __name__ == "__main__":
    sys.exit(main())
