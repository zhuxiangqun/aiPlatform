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


def cyan(text: str) -> str:
    return f"\033[0;36m{text}\033[0m"


# Baseline ratchet (mirrors guard_frontend.py §45 + guard_ast_behavior except:pass):
# lock the CURRENT set of ERROR-level violations as known debt → exit 0; only NEW
# error-level violations (signature not in baseline) block (exit 1). Without this,
# the guard exits 1 forever on documented known-debt and gets ignored ("cried wolf").
ARCH_BASELINE = WORKSPACE_ROOT / "scripts" / "baselines" / "architecture_guard_baseline.txt"


def _arch_error_sigs(report) -> dict:
    """Stable signatures for ERROR-level violations (these drive report.violations/ok).

    Signature = '§<section>:<code>' — stable across runs (no line numbers, no counts).
    """
    sigs = {}
    for section in report.sections:
        for item in getattr(section, "items", []) or []:
            if getattr(item, "level", "") == "error":
                sigs[f"{section.number}:{item.code}"] = item
    return sigs


def _load_arch_baseline() -> set:
    try:
        return {
            ln.strip()
            for ln in ARCH_BASELINE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
    except Exception:
        return set()


def _write_arch_baseline(sigs) -> None:
    ARCH_BASELINE.parent.mkdir(parents=True, exist_ok=True)
    ARCH_BASELINE.write_text("\n".join(sorted(sigs)) + "\n", encoding="utf-8")


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
            if item.level == "info":
                tag = "INFO"
            elif not item.files:
                tag = "PASS"
            elif item.level == "warning":
                tag = "WARN"
            else:
                tag = "FAIL"
            color_func = {"PASS": green, "WARN": yellow, "FAIL": red, "INFO": cyan}
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


def _expand_diff_to_affected(repo_root: Path, changed_files: list) -> list:
    """Expand git diff to include downstream callers via CodeGraph.
    
    max_depth=1: only direct callers of changed files.
    max_files=50: if expansion exceeds this, return changed_files as-is
    (fall back to full scan — it's slower but safer than missing issues).
    """
    MAX_DEPTH = 1
    MAX_FILES = 50

    if not changed_files:
        return changed_files

    try:
        sys.path.insert(0, str(repo_root / "aiPlat-core"))
        from core.harness.knowledge.code_graph import (
            _extract_symbols_ast, build_graph, repo_root as _repo_root_fn,
        )
        from pathlib import Path as _Path

        # Build graph (cached, so fast)
        repo = _repo_root_fn()
        if not repo:
            return changed_files
        nodes, edges, _issues = build_graph(repo, [repo])

        # Collect all symbols exported by changed files
        all_symbols = set()
        for f in changed_files:
            try:
                fp = _Path(f)
                if fp.exists() and fp.suffix == ".py":
                    symbols = _extract_symbols_ast(fp)
                    all_symbols.update(s.name for s in symbols if hasattr(s, 'name'))
            except Exception:
                pass

        if not all_symbols:
            return changed_files

        # Find files that import/call these symbols (incoming edges)
        expanded = set(changed_files)
        for depth in range(MAX_DEPTH):
            new_files = set()
            for edge in edges:
                source = edge.get("source", "")
                target = edge.get("target", "")
                target_file = edge.get("target_file", "")
                if target in all_symbols or target_file in changed_files:
                    if source not in expanded:
                        new_files.add(source)
            expanded.update(new_files)
            if len(expanded) > MAX_FILES:
                return changed_files  # too broad — fall back to full scan

        return list(expanded)
    except Exception:
        return changed_files


def main():
    parser = argparse.ArgumentParser(description="Architecture Guard")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--quick", action="store_true", help="Quick mode (imports only)")
    parser.add_argument("--diff-only", action="store_true", help="Only scan git-changed files + CodeGraph callers")
    parser.add_argument("--write-baseline", action="store_true", help="Regenerate the ERROR-level baseline ratchet")
    args = parser.parse_args()

    # ── --diff-only: expand changed files via CodeGraph for faster PR CI ──
    if args.diff_only:
        try:
            import subprocess as _sp
            result = _sp.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, timeout=10,
                cwd=str(WORKSPACE_ROOT),
            )
            changed = [f for f in result.stdout.splitlines() if f.endswith(".py")]
            if not changed:
                sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))
                from core.management.arch_guard_base import ArchReport, ArchSection, ArchIssue
                print(format_text(ArchReport(ok=True, violations=0, duration_ms=0, sections=[
                    ArchSection(number="§diff", name="Diff-Only Scan", status="pass",
                               items=[ArchIssue(level="pass", code="diff_ok",
                                                message="No Python files changed — skipping full scan")])
                ])))
                sys.exit(0)
            expanded = _expand_diff_to_affected(WORKSPACE_ROOT, changed)
            diff_count = len(expanded) if expanded else len(changed)
            print(f"\n  [diff-only] {len(changed)} changed + {diff_count - len(changed)} affected = {diff_count} files to scan")
            if diff_count <= 50:
                os.environ["AIPLAT_ARCH_GUARD_SCAN_FILES"] = ",".join(expanded)
            else:
                print(f"  [diff-only] expanded set exceeds 50 files ({diff_count}) — running full scan")
        except Exception:
            pass

    # Import the registry (needs repo in path)
    sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))
    from core.management.arch_guard_base import get_arch_registry

    registry = get_arch_registry()
    report = registry.run_all(WORKSPACE_ROOT)

    # ── Baseline ratchet: lock known ERROR-level debt, fail only on NEW ──
    error_sigs = _arch_error_sigs(report)
    if args.write_baseline:
        _write_arch_baseline(set(error_sigs))
        print(f"PASS: architecture_guard baseline written = {len(error_sigs)} error signatures")
        sys.exit(0)

    baseline = _load_arch_baseline()
    new_sigs = sorted(s for s in error_sigs if s not in baseline)
    known_sigs = sorted(s for s in error_sigs if s in baseline)

    if args.json:
        output = {
            "ok": report.ok,
            "violations": report.violations,
            "new_violations": new_sigs,
            "baseline_violations": known_sigs,
            "duration_ms": report.duration_ms,
            "summary": report.summary,
            "sections": [s.to_dict() for s in report.sections],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_text(report))
        print("")
        if new_sigs:
            print(red(f"═══ ARCH GUARD RATCHET: {len(new_sigs)} NEW error violation(s) — not in baseline ═══"))
            for s in new_sigs:
                print(red(f"  [NEW] {s}"))
            print("  → Fix the violation, or (if intentional) run: "
                  "python scripts/architecture_guard.py --write-baseline")
        else:
            print(green(f"═══ ARCH GUARD RATCHET: 0 new, {len(known_sigs)} baseline known-debt error(s) — OK ═══"))

    sys.exit(1 if new_sigs else 0)


if __name__ == "__main__":
    main()
