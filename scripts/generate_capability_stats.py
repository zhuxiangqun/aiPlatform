#!/usr/bin/env python3
"""
generate_capability_stats.py — regenerate CAPABILITIES AUTO-STATS block (Phase C)

Source of truth = chapter ✅/⚠️ rows in AIPLAT_CAPABILITIES.md.
The stats table between AUTO-STATS:BEGIN/END is a pure generated view.

Usage:
  python3 scripts/generate_capability_stats.py           # rewrite worktree
  python3 scripts/generate_capability_stats.py --ci      # freshness check only (exit 1 if stale)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _load():
    path = SCRIPTS / "verify_capability_consistency.py"
    spec = importlib.util.spec_from_file_location("verify_capability_consistency", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    v = _load()
    if "--ci" in argv:
        return v.check_stats_fresh()
    v.fix()
    return v.check_stats_fresh()


if __name__ == "__main__":
    sys.exit(main())
