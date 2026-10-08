#!/usr/bin/env python3
"""check_team_routing_mode.py — W5: seed/team YAML must default to static routing.

Fails (exit 1) if any workspace seed team sets routing_mode to llm/moa/swarm/
roundtable/debate without an explicit ``# routing-ok: <reason>`` on the same
or previous line. Production LLM supervisor additionally requires
AIPLAT_DYNAMIC_ROUTER_ENABLED + PERCENTAGE (see pipeline_engine).

Usage:
  python3 scripts/check_team_routing_mode.py
  python3 scripts/check_team_routing_mode.py --ci
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

WORKSPACE = Path(__file__).resolve().parents[1]
SEED_DIRS = [
    WORKSPACE / "aiPlat-core/core/workspace_seeds/teams",
]
RISKY = frozenset({"llm", "moa", "swarm", "roundtable", "debate"})
OK_MARK = "# routing-ok:"


def _routing_mode_value(stripped: str) -> str | None:
    """Parse `routing_mode: X` or list item `- routing_mode: X`."""
    if stripped.startswith("- "):
        stripped = stripped[2:].strip()
    if not stripped.startswith("routing_mode:"):
        return None
    return stripped.split(":", 1)[1].strip().strip("\"'").lower()


def _scan_file(path: Path) -> List[str]:
    violations: List[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        val = _routing_mode_value(line.strip())
        if val is None:
            continue
        if val in ("", "static", "off", "none", "chain"):
            continue
        if val not in RISKY:
            continue
        prev = lines[i - 1] if i > 0 else ""
        if OK_MARK not in line and OK_MARK not in prev:
            try:
                rel = path.relative_to(WORKSPACE)
            except ValueError:
                rel = path
            violations.append(
                f"{rel}:{i + 1}: routing_mode={val!r} without `{OK_MARK} <reason>` "
                "(W5: LLM supervisor / multi-mode must be explicit)"
            )
    return violations


def check(paths: List[Path] | None = None) -> Tuple[List[str], int]:
    files: List[Path] = []
    for d in paths or SEED_DIRS:
        if d.is_dir():
            files.extend(sorted(d.glob("*.yaml")))
            files.extend(sorted(d.glob("*.yml")))
    violations: List[str] = []
    for f in files:
        violations.extend(_scan_file(f))
    return violations, len(files)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ci", action="store_true")
    args = ap.parse_args(argv)
    violations, nfiles = check()
    for v in violations:
        print(f"FAIL: {v}")
    print(f"summary: files={nfiles} violations={len(violations)}")
    if violations:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
