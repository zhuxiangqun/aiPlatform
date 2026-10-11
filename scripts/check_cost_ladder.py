#!/usr/bin/env python3
"""E4 residual: cost-ladder ratchet for new Syscall / MCP seeds.

CLAUDE.md §20 — Syscall and MCP are expensive rungs. New defs must be
registered in AIPLAT_CAPABILITIES.md and/or marked ``# ladder-ok:`` near
the definition (or in server.yaml).

Usage:
  python3 scripts/check_cost_ladder.py --check
  python3 scripts/check_cost_ladder.py --rebuild
  python3 scripts/check_cost_ladder.py --check --staged
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

WORKSPACE = Path(__file__).resolve().parent.parent
SYSCALL_BASELINE = WORKSPACE / "scripts" / "baselines" / "cost_ladder_syscalls.txt"
MCP_BASELINE = WORKSPACE / "scripts" / "baselines" / "cost_ladder_mcps.txt"
CAPABILITIES = WORKSPACE / "AIPLAT_CAPABILITIES.md"

SYSCALL_ROOT = WORKSPACE / "aiPlat-core" / "core" / "harness" / "syscalls"
MCP_SEED_DIRS = [
    WORKSPACE / "aiPlat-core" / "workspace_seeds" / "mcps",
    WORKSPACE / "aiPlat-core" / "core" / "workspace_seeds" / "mcps",
]

_DEF_RE = re.compile(r"^(?:async\s+)?def\s+(sys_[a-z0-9_]+)\s*\(", re.M)
_LADDER_OK_RE = re.compile(r"#\s*ladder-ok\b", re.I)


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(WORKSPACE))
    except ValueError:
        return str(p)


def scan_syscalls() -> Dict[str, str]:
    """Return {relpath:sys_name → source file content snippet for ladder-ok}."""
    found: Dict[str, str] = {}
    if not SYSCALL_ROOT.is_dir():
        return found
    for py in sorted(SYSCALL_ROOT.rglob("*.py")):
        if py.name.startswith("_") or "/tests/" in str(py):
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        rel = _rel(py)
        for m in _DEF_RE.finditer(text):
            key = f"{rel}:{m.group(1)}"
            # Window: 3 lines before def for # ladder-ok
            start = max(0, m.start() - 240)
            found[key] = text[start : m.end()]
    return found


def scan_mcps() -> Dict[str, str]:
    """Return {mcp_dir_name → server.yaml text}."""
    found: Dict[str, str] = {}
    for root in MCP_SEED_DIRS:
        if not root.is_dir():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            yml = d / "server.yaml"
            if yml.is_file():
                found[d.name] = yml.read_text(encoding="utf-8", errors="replace")
    return found


def load_baseline(path: Path) -> Set[str]:
    if not path.is_file():
        return set()
    out: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.add(s)
    return out


def write_baseline(path: Path, keys: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(sorted(keys)) + ("\n" if keys else "")
    path.write_text(body, encoding="utf-8")


def _caps_text() -> str:
    if CAPABILITIES.is_file():
        return CAPABILITIES.read_text(encoding="utf-8", errors="replace")
    return ""


def _staged_paths() -> Set[str]:
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return set()
    return {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}


def check(*, staged_only: bool = False) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings)."""
    errors: List[str] = []
    warnings: List[str] = []
    caps = _caps_text()
    staged = _staged_paths() if staged_only else set()

    base_sys = load_baseline(SYSCALL_BASELINE)
    current_sys = scan_syscalls()
    new_sys = sorted(set(current_sys) - base_sys)
    for key in new_sys:
        rel, name = key.split(":", 1)
        if staged_only and rel not in staged:
            continue
        snippet = current_sys.get(key, "")
        has_ok = bool(_LADDER_OK_RE.search(snippet))
        in_caps = name in caps
        if has_ok or in_caps:
            if not in_caps:
                warnings.append(
                    f"syscall {name} has # ladder-ok but missing AIPLAT_CAPABILITIES.md entry"
                )
            continue
        errors.append(
            f"new syscall {key} beyond baseline — add CAPABILITIES row and/or "
            f"`# ladder-ok: L6 — why 1-5 infeasible` above the def; then "
            f"`python3 scripts/check_cost_ladder.py --rebuild`"
        )

    base_mcp = load_baseline(MCP_BASELINE)
    current_mcp = scan_mcps()
    new_mcp = sorted(set(current_mcp) - base_mcp)
    for name in new_mcp:
        # staged path match either seed tree
        if staged_only:
            hit = any(
                f.endswith(f"mcps/{name}/server.yaml") for f in staged
            )
            if not hit:
                continue
        text = current_mcp.get(name, "")
        has_ok = bool(_LADDER_OK_RE.search(text))
        in_caps = name in caps or f"mcps/{name}" in caps
        if has_ok or in_caps:
            if not in_caps:
                warnings.append(
                    f"MCP {name} has # ladder-ok but missing AIPLAT_CAPABILITIES.md entry"
                )
            continue
        errors.append(
            f"new MCP seed {name!r} beyond baseline — document in CAPABILITIES "
            f"and/or `# ladder-ok:` in server.yaml; then "
            f"`python3 scripts/check_cost_ladder.py --rebuild`"
        )

    return errors, warnings


def cmd_rebuild() -> int:
    sys_keys = sorted(scan_syscalls())
    mcp_keys = sorted(scan_mcps())
    write_baseline(SYSCALL_BASELINE, sys_keys)
    write_baseline(MCP_BASELINE, mcp_keys)
    print(f"Rebuilt {SYSCALL_BASELINE.relative_to(WORKSPACE)} ({len(sys_keys)} syscalls)")
    print(f"Rebuilt {MCP_BASELINE.relative_to(WORKSPACE)} ({len(mcp_keys)} mcps)")
    return 0


def cmd_check(*, staged_only: bool = False) -> int:
    errors, warnings = check(staged_only=staged_only)
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        print(f"FAIL: cost ladder — {len(errors)} finding(s)")
        for e in errors:
            print(f"  ❌ {e}")
        return 1
    print("PASS: cost ladder (syscall/MCP) clean")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Cost ladder ratchet (syscall / MCP)")
    ap.add_argument("--check", action="store_true", help="Fail on new entries without justification")
    ap.add_argument("--rebuild", action="store_true", help="Rewrite baselines from disk")
    ap.add_argument(
        "--staged",
        action="store_true",
        help="Only consider paths in git staged set (pre-commit)",
    )
    args = ap.parse_args()
    if args.rebuild:
        return cmd_rebuild()
    if args.check or not args.rebuild:
        return cmd_check(staged_only=args.staged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
