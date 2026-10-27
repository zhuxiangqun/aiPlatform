#!/usr/bin/env python3
"""DEPRECATED wrapper — synthetic RUNLOG path removed.

Use:
  bash scripts/slice_e2e.sh --scenario lock-service
  bash scripts/slice_e2e.sh --scenario lock-service --inject disconnect

This entrypoint only delegates to slice_e2e.sh (tmp/ output, live Gate3 evidence).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "slice_e2e.sh"


def main() -> int:
    # Forward CLI args; env SLICE_E2E_INJECT only fills --inject when absent.
    args = list(sys.argv[1:])
    if "--scenario" not in args:
        args = ["--scenario", "lock-service", *args]
    inject_env = os.environ.get("SLICE_E2E_INJECT", "").strip()
    if inject_env and "--inject" not in args:
        args.extend(["--inject", inject_env])
    cmd = ["bash", str(SCRIPT), *args]
    print(
        "NOTE: five_products_slice_smoke.py no longer writes synthetic smoke_ok; "
        "delegating to slice_e2e.sh",
        file=sys.stderr,
    )
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
