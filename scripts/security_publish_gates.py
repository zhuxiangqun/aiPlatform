#!/usr/bin/env python3
"""Single entry for security publish gates (Ops runbook 3c).

Modes:
  ledger   — default CI / engineering (ledger_ok)
  release  — ordinary product publish (ledger ∧ accounted ∧ release)
  claim    — external security claim only (ledger ∧ coverage)

Never sets security_certification. Does not bypass release_blocking /
release_risk_acceptance rules in security_dimensions_report.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "scripts" / "security_dimensions_report.py"

MODE_FLAGS = {
    "ledger": [],
    "release": ["--release-gate"],
    "claim": ["--claim-gate"],
}


def _run(mode: str) -> subprocess.CompletedProcess:
    flags = MODE_FLAGS[mode]
    return subprocess.run(
        [sys.executable, str(REPORT), *flags],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """main。

    Args:
        argv: argv 参数。
    """
    parser = argparse.ArgumentParser(description="Security publish gates wrapper")
    parser.add_argument(
        "--mode",
        choices=sorted(MODE_FLAGS),
        default="ledger",
        help="ledger (CI) | release (ordinary publish) | claim (external claim)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print dimensions report JSON even when wrapping gates",
    )
    args = parser.parse_args(argv)

    proc = _run(args.mode)
    payload = {}
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"parse_error": True, "stdout": (proc.stdout or "")[:500]}

    out = {
        "schema": "eval.security_publish_gates.v1",
        "mode": args.mode,
        "exit": proc.returncode,
        "ok": proc.returncode == 0,
        "ledger_ok": payload.get("ledger_ok"),
        "accounted_ok": payload.get("accounted_ok"),
        "release_ok": payload.get("release_ok"),
        "coverage_ok": payload.get("coverage_ok"),
        "release_blocking_ids": payload.get("release_blocking_ids"),
        "open_gap_ids": payload.get("open_gap_ids"),
        "security_certification": False,
        "honesty": (
            "Wrapper only. Ordinary publish must use --mode release. "
            "Claim mode is for external statements only. ≠ certification."
        ),
    }
    if args.json:
        out["report"] = payload
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
