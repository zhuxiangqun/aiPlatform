#!/usr/bin/env python3
"""check_asset_compat_gates.py — COMPAT honesty static gates (Phase D wrap / clause 85).

Asserts source still wires:
  - ToolDiscovery: is_tool_schedulable + register_with_report
  - Tool lifecycle: published/listed listing COMPAT assert
  - sys_tool_call: is_tool_schedulable hard gate
  - sys_skill_call: is_skill_schedulable hard gate (Phase A)

Usage:
  python3 scripts/check_asset_compat_gates.py
  python3 scripts/check_asset_compat_gates.py --ci
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
CORE = WORKSPACE / "aiPlat-core" / "core"

CHECKS = [
    {
        "path": CORE / "apps" / "tools" / "discovery.py",
        "needles": ("is_tool_schedulable", "register_with_report", "def register_with_report"),
        "label": "ToolDiscovery COMPAT hot-load gate",
    },
    {
        "path": CORE / "apps" / "tools" / "lifecycle.py",
        "needles": (
            "_assert_tool_compat_schedulable_for_listing",
            "published",
            "listed",
            "is_tool_schedulable",
        ),
        "label": "Tool listing COMPAT gate",
    },
    {
        "path": CORE / "harness" / "syscalls" / "tool.py",
        "needles": ("is_tool_schedulable", "tool_schedulable_error"),
        "label": "sys_tool_call COMPAT gate",
    },
    {
        "path": CORE / "harness" / "syscalls" / "skill.py",
        "needles": ("is_skill_schedulable", "skill_schedulable_error"),
        "label": "sys_skill_call COMPAT gate",
    },
]


def run() -> list[str]:
    violations: list[str] = []
    for spec in CHECKS:
        path: Path = spec["path"]
        if not path.is_file():
            violations.append(f"MISSING {path.relative_to(WORKSPACE)} ({spec['label']})")
            continue
        text = path.read_text(encoding="utf-8")
        missing = [n for n in spec["needles"] if n not in text]
        if missing:
            rel = path.relative_to(WORKSPACE)
            violations.append(
                f"{rel}: missing {missing!r} for {spec['label']}"
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ci", action="store_true", help="exit 1 on violations")
    args = ap.parse_args(argv)
    violations = run()
    if not violations:
        print("OK: asset compat gates present (discovery/lifecycle/sys_tool/sys_skill)")
        return 0
    print("FAIL: asset compat gate regressions:")
    for v in violations:
        print(f"  - {v}")
    return 1 if args.ci else 1


if __name__ == "__main__":
    sys.exit(main())
