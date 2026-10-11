#!/usr/bin/env python3
"""Weekly / on-demand post-merge repo health scan → duty-board JSONL.

Usage:
  python3 scripts/scan_repo_health.py
  python3 scripts/scan_repo_health.py --no-persist
  python3 scripts/scan_repo_health.py --summary
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
    ap = argparse.ArgumentParser(description="Scan repo health (post-merge boiling-frog metrics)")
    ap.add_argument("--summary", action="store_true", help="assess existing JSONL only")
    ap.add_argument("--no-persist", action="store_true", help="scan without appending JSONL")
    ap.add_argument("--json", action="store_true", help="print full assess JSON")
    args = ap.parse_args()

    _ensure_path()
    from core.harness.meta.repo_health_scan import (
        append_health_snapshot,
        assess_repo_health,
        list_health_snapshots,
        scan_repo_health,
    )

    persisted = None
    if args.summary:
        result = assess_repo_health()
    else:
        metrics = scan_repo_health()
        if not args.no_persist:
            persisted = append_health_snapshot(metrics)
            result = assess_repo_health()
        else:
            prior = list_health_snapshots(limit=49)
            result = assess_repo_health(snapshots=list(prior) + [metrics])
        result["persisted"] = persisted

    sev = str(result.get("severity") or "unavailable")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        latest = result.get("latest") or {}
        print(
            f"repo_health={sev} loc={latest.get('py_loc')} "
            f"god={latest.get('god_files')} multi_base={latest.get('multi_base_classes')} "
            f"fanout={latest.get('high_fanout_files')} deps={latest.get('dep_entries')} "
            f"snapshots={result.get('n_snapshots')}"
        )
        for r in (result.get("reasons") or [])[:5]:
            print(f"  · {r}")
        if persisted:
            print(f"  persisted: {persisted}")
    return 2 if sev == "block" else 0


if __name__ == "__main__":
    sys.exit(main())
