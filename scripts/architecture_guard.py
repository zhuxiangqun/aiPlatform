#!/usr/bin/env python3
"""
Architecture Guard — CLI entry point.

Replaces the bash-based architecture_guard.sh with a Python RuleRegistry engine.
Backward compatible text output + JSON mode for API consumption.

Usage:
  python scripts/architecture_guard.py          # Text output (like .sh)
  python scripts/architecture_guard.py --json   # JSON output
  python scripts/architecture_guard.py --quick  # Quick mode (imports only)
"""

import argparse
import json
import sys
from pathlib import Path

# Workspace root is parent of scripts/
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def red(text: str) -> str:
    return f"\033[0;31m{text}\033[0m"


def green(text: str) -> str:
    return f"\033[0;32m{text}\033[0m"


def yellow(text: str) -> str:
    return f"\033[0;33m{text}\033[0m"


def format_text(report) -> str:
    """Format ArchReport as text matching the original .sh output."""
    lines = []
    lines.append("")
    lines.append("═" * 63)
    lines.append("  ARCHITECTURE GUARD: Checking layers + compliance")
    lines.append("═" * 63)

    for section in report.sections:
        lines.append("")
        lines.append("═" * 63)
        lines.append(f"  {section.number}: {section.name}")
        lines.append("═" * 63)

        if not section.items:
            lines.append("")
            lines.append(f"  {green('[PASS]')}  all checks pass")
            continue

        for item in section.items:
            tag = "PASS" if not item.files else ("WARN" if item.level == "warning" else "FAIL")
            color_func = {"PASS": green, "WARN": yellow, "FAIL": red}
            cf = color_func.get(tag, lambda x: x)
            lines.append("")
            if item.files:
                lines.append(f"  {cf(f'[{tag}]')}  {item.message} — {len(item.files)} violation(s)")
                for f in item.files[:5]:
                    lines.append(f"        {cf('→')} {f}")
                if len(item.files) > 5:
                    lines.append(f"        ... and {len(item.files) - 5} more")
            elif item.count > 0:
                lines.append(f"  {cf(f'[{tag}]')}  {item.message} — {item.count} violation(s)")
            else:
                lines.append(f"  {cf(f'[{tag}]')}  {item.message}")

    lines.append("")
    lines.append("═" * 63)
    if report.ok:
        lines.append(green("═══ ARCHITECTURE GUARD PASSED — all layers compliant ═══"))
    else:
        lines.append(red(f"═══ ARCHITECTURE GUARD FAILED: {report.violations} violations ═══"))
        lines.append("")
        lines.append("  These violations block merge. Fix options:")
        lines.append("  1. Move code to the correct layer")
        lines.append("  2. Use the approved facade/API pattern")
        lines.append("  3. Replace hardcoded values with configuration fields")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Architecture Guard")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--quick", action="store_true", help="Quick mode (imports only)")
    args = parser.parse_args()

    # Import the registry (needs repo in path)
    sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))
    from core.management.arch_guard_base import get_arch_registry

    registry = get_arch_registry()
    report = registry.run_all(WORKSPACE_ROOT)

    if args.json:
        output = {
            "ok": report.ok,
            "violations": report.violations,
            "duration_ms": report.duration_ms,
            "summary": report.summary,
            "sections": [s.to_dict() for s in report.sections],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_text(report))

    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
