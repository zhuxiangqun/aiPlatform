#!/usr/bin/env python3
"""
ruff_f821_ratchet.py — F821 undefined-name baseline ratchet engine.

Compares current ruff F821 output against a JSON baseline.
Fails only on NEW violations (new files or new symbol names in existing files).

Usage (called by ruff_f821_ratchet.sh):
    python3 scripts/ruff_f821_ratchet.py --rebuild    # rebuild baseline
    python3 scripts/ruff_f821_ratchet.py --check       # check against baseline
    python3 scripts/ruff_f821_ratchet.py --advisory    # report only, don't fail
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = WORKSPACE_ROOT / "scripts" / "ruff_f821_baseline.json"

SCAN_DIRS = [
    "aiPlat-core/core",
    "aiPlat-platform",
    "aiPlat-infra",
    "aiPlat-app",
    "aiPlat-management",
]


def _resolve_scan_dirs() -> list[Path]:
    dirs = []
    for d in SCAN_DIRS:
        full = WORKSPACE_ROOT / d
        if full.is_dir():
            dirs.append(full)
    return dirs


def _run_ruff() -> dict[str, set[str]]:
    """Run ruff F821 on all scan dirs. Returns {filepath: {symbol, ...}}."""
    current: dict[str, set[str]] = {}
    for scan_dir in _resolve_scan_dirs():
        result = subprocess.run(
            ["ruff", "check", "--select", "F821", "--output-format", "concise", str(scan_dir)],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            if "F821" not in line:
                continue
            # Format: "file.py:line:col: F821 Undefined name `symbol`"
            parts = line.split(" F821 Undefined name ", 1)
            if len(parts) != 2:
                continue
            # parts[0] = "file.py:line:col:"
            # parts[1] = "`symbol`"
            fpath = parts[0].rstrip(" :0123456789").strip()
            symbol = parts[1].strip().strip("`")

            # Skip test files
            if "/tests/" in fpath or "__pycache__" in fpath or ".venv" in fpath:
                continue

            # Make path relative to workspace root for consistency
            try:
                rel = str(Path(fpath).relative_to(WORKSPACE_ROOT))
            except ValueError:
                rel = fpath

            if rel not in current:
                current[rel] = set()
            current[rel].add(symbol)

    return current


def cmd_rebuild() -> None:
    """Rebuild the baseline from current F821 violations."""
    current = _run_ruff()
    files_bl = {}
    for fpath, symbols in sorted(current.items()):
        files_bl[fpath] = {
            "count": len(symbols),
            "symbols": sorted(symbols),
        }

    baseline = {
        "_comment": "ruff F821 baseline. Rebuild: bash scripts/ruff_f821_ratchet.sh --rebuild",
        "_generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_total_files": len(files_bl),
        "_total_violations": sum(v["count"] for v in files_bl.values()),
        "files": files_bl,
    }

    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2, sort_keys=True, default=str)

    total_v = baseline["_total_violations"]
    print(f"Baseline written: {len(files_bl)} files, {total_v} violations")
    print(f"  Commit this file so CI can compare: {BASELINE_FILE}")


def cmd_advisory() -> None:
    """Print F821 violations without failing."""
    current = _run_ruff()
    total = sum(len(s) for s in current.values())
    print(f"F821 advisory: {len(current)} files, {total} violations (non-fatal)")
    for fpath, symbols in sorted(current.items()):
        if len(symbols) <= 3:
            print(f"  {fpath}: {', '.join(sorted(symbols))}")
        else:
            first3 = ", ".join(sorted(symbols)[:3])
            print(f"  {fpath}: {first3} ... and {len(symbols)-3} more")
    if total == 0:
        print("  (no violations)")


def cmd_check() -> int:
    """Check current F821 violations against baseline. Returns exit code."""
    if not BASELINE_FILE.exists():
        print(f"ERROR: Baseline not found at {BASELINE_FILE}")
        print("  Run: bash scripts/ruff_f821_ratchet.sh --rebuild")
        return 1

    with open(BASELINE_FILE) as f:
        bl_data = json.load(f)
    bl_files = bl_data.get("files", {})

    current = _run_ruff()

    new_files: list[str] = []
    new_symbols: list[str] = []
    improved: list[str] = []

    for fpath, cur_syms in sorted(current.items()):
        if fpath not in bl_files:
            first5 = ", ".join(sorted(cur_syms)[:5])
            new_files.append(f"{fpath} ({len(cur_syms)} violations: {first5})")
            continue
        bl_syms = set(bl_files[fpath].get("symbols", []))
        extra = cur_syms - bl_syms
        missing = bl_syms - cur_syms
        if extra:
            for sym in sorted(extra):
                new_symbols.append(f"{fpath}: new F821 symbol '{sym}'")
        if missing:
            improved.append(f"{fpath}: {len(bl_syms)} -> {len(cur_syms)} (-{len(missing)})")
        elif len(cur_syms) < len(bl_syms):
            improved.append(f"{fpath}: {len(bl_syms)} -> {len(cur_syms)} (shrunk)")

    for fpath in sorted(bl_files):
        if fpath not in current:
            improved.append(f"{fpath}: {bl_files[fpath]['count']} -> 0 (CLEAN)")

    # Output
    bl_total = sum(v["count"] for v in bl_files.values())
    cur_total = sum(len(v) for v in current.values())
    print(f"Baseline: {len(bl_files)} files, {bl_total} violations")
    print(f"Current:  {len(current)} files, {cur_total} violations")
    print()

    if new_files:
        print(f"NEW FILES ({len(new_files)}):")
        for f in new_files:
            print(f"  {f}")
        print()

    if new_symbols:
        print(f"NEW SYMBOLS ({len(new_symbols)}):")
        for s in new_symbols:
            print(f"  {s}")
        print()

    if improved:
        print(f"IMPROVED ({len(improved)}):")
        for i in improved:
            print(f"  {i}")
        print()

    if new_files or new_symbols:
        print(f"FAIL: {len(new_files)} new files + {len(new_symbols)} new symbols beyond baseline")
        print()
        print("  Fix options:")
        print("  1. Add the missing import to the file")
        print("  2. If intentional (Mixin pattern reusing base-class symbols),")
        print("     run: bash scripts/ruff_f821_ratchet.sh --rebuild")
        print("     and commit the updated baseline")
        return 1

    print("PASS: no new F821 violations above baseline")
    if improved:
        print("  Tip: run --rebuild to lower the baseline after improvements")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="ruff F821 ratchet checker")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild baseline from current state")
    parser.add_argument("--check", action="store_true", help="Check against baseline (default)")
    parser.add_argument("--advisory", action="store_true", help="Report violations without failing")
    args = parser.parse_args()

    if args.rebuild:
        cmd_rebuild()
    elif args.advisory:
        cmd_advisory()
    else:
        sys.exit(cmd_check())


if __name__ == "__main__":
    main()
