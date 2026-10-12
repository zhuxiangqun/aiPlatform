#!/usr/bin/env python3
"""E4 / O1: cost-ladder ratchet for new Syscall / MCP seeds.

CLAUDE.md §20 — Syscall and MCP are expensive rungs. New defs must carry
a quality proof (template fields) and/or a valid ``# ladder-ok:`` comment
(min reason length; optional ``temporary until <date>``).

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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
_LADDER_OK_RE = re.compile(
    r"#\s*ladder-ok\s*:\s*(.+?)(?:\n|$)",
    re.I,
)
_TEMP_UNTIL_RE = re.compile(
    r"temporary\s+until\s+(\d{4}-\d{2}-\d{2}(?:[T ][\d:+\-Z]+)?)",
    re.I,
)
_PROOF_KEYS = (
    "why_not_1_extend",
    "why_not_2_cli",
    "why_not_3_tool",
    "why_not_4_plugin",
    "rung",
    "blast_radius",
)
_PLACEHOLDER_RE = re.compile(
    r"^(n/?a|tbd|todo|待补|占位|none|null|\.+|xxx+)$",
    re.I,
)
_MIN_WHY = 20
_MIN_LADDER_REASON = 15


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(WORKSPACE))
    except ValueError:
        return str(p)


def _parse_until(raw: str) -> Optional[datetime]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            s = s + "T23:59:59+00:00"
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def parse_ladder_ok(text: str) -> Tuple[bool, str]:
    """Return (ok, error_or_empty). Validates inline ``# ladder-ok:`` quality."""
    m = _LADDER_OK_RE.search(text or "")
    if not m:
        return False, "missing # ladder-ok: <reason>"
    reason = (m.group(1) or "").strip()
    if not reason:
        return False, "# ladder-ok reason empty"
    temp = _TEMP_UNTIL_RE.search(reason)
    if temp:
        until = _parse_until(temp.group(1))
        if until is None:
            return False, f"# ladder-ok temporary until date invalid: {temp.group(1)!r}"
        if until <= datetime.now(timezone.utc):
            return False, f"# ladder-ok temporary until expired ({temp.group(1)})"
        # strip temporary clause for length check on remaining rationale
        reason_body = _TEMP_UNTIL_RE.sub("", reason).strip(" :,-")
        if len(reason_body) < _MIN_LADDER_REASON and len(reason) < _MIN_LADDER_REASON + 20:
            # allow full line to count if temporary clause is the bulk
            if len(reason) < _MIN_LADDER_REASON:
                return False, f"# ladder-ok reason < {_MIN_LADDER_REASON} chars"
        return True, ""
    if len(reason) < _MIN_LADDER_REASON:
        return False, f"# ladder-ok reason < {_MIN_LADDER_REASON} chars ({len(reason)})"
    if _PLACEHOLDER_RE.match(reason):
        return False, f"# ladder-ok reason looks like placeholder: {reason!r}"
    return True, ""


def parse_proof_block(text: str) -> Tuple[bool, List[str]]:
    """Parse proof template fields; return (ok, error messages)."""
    errors: List[str] = []
    fields: Dict[str, str] = {}
    for key in _PROOF_KEYS:
        m = re.search(
            rf"(?:^|\n)\s*{re.escape(key)}\s*:\s*(.+?)(?:\n|$)",
            text or "",
            re.I,
        )
        fields[key] = (m.group(1).strip() if m else "")
    for key in _PROOF_KEYS[:4]:
        val = fields.get(key, "")
        if not val:
            errors.append(f"missing {key}")
        elif len(val) < _MIN_WHY:
            errors.append(f"{key} < {_MIN_WHY} chars ({len(val)})")
        elif _PLACEHOLDER_RE.match(val):
            errors.append(f"{key} placeholder: {val!r}")
    rung = fields.get("rung", "").strip()
    if rung.upper() not in ("MCP", "SYSCALL"):
        errors.append(f"rung must be MCP|Syscall (got {rung!r})")
    blast = fields.get("blast_radius", "")
    if not blast:
        errors.append("missing blast_radius")
    elif len(blast) < _MIN_WHY:
        errors.append(f"blast_radius < {_MIN_WHY} chars")
    elif _PLACEHOLDER_RE.match(blast):
        errors.append(f"blast_radius placeholder: {blast!r}")
    else:
        low = blast.lower()
        if not any(tok in low for tok in ("fail", "token", "权限", "permission", "blast", "失败")):
            errors.append(
                "blast_radius must mention failure/token/permission impact"
            )
    return (not errors), errors


def justification_ok(local_text: str, caps_window: str = "") -> Tuple[bool, str]:
    """Accept full proof block OR valid # ladder-ok (v1.9 quality gate)."""
    blob = f"{local_text or ''}\n{caps_window or ''}"
    proof_ok, proof_errs = parse_proof_block(blob)
    if proof_ok:
        return True, ""
    ok, err = parse_ladder_ok(blob)
    if ok:
        return True, ""
    parts = []
    if proof_errs:
        parts.append("proof: " + "; ".join(proof_errs[:4]))
    if err:
        parts.append(err)
    if not parts:
        parts.append("need proof template or # ladder-ok: <reason≥15>")
    return False, " | ".join(parts)


def _caps_window_for(name: str, caps: str, *, radius: int = 1200) -> str:
    if not name or not caps:
        return ""
    idx = caps.find(name)
    if idx < 0:
        return ""
    return caps[max(0, idx - radius) : idx + radius]


def scan_syscalls() -> Dict[str, str]:
    """Return {relpath:sys_name → source window for ladder-ok / proof}."""
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
            start = max(0, m.start() - 800)
            found[key] = text[start : m.end() + 200]
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
        caps_win = _caps_window_for(name, caps)
        in_caps = name in caps
        ok, detail = justification_ok(snippet, caps_win)
        if ok:
            if not in_caps:
                warnings.append(
                    f"syscall {name} justified but missing AIPLAT_CAPABILITIES.md entry"
                )
            continue
        errors.append(
            f"new syscall {key} beyond baseline — quality proof failed ({detail}). "
            f"Add proof template and/or `# ladder-ok: <reason≥15>` "
            f"(optional `temporary until YYYY-MM-DD`); then "
            f"`python3 scripts/check_cost_ladder.py --rebuild`"
        )

    base_mcp = load_baseline(MCP_BASELINE)
    current_mcp = scan_mcps()
    new_mcp = sorted(set(current_mcp) - base_mcp)
    for name in new_mcp:
        if staged_only:
            hit = any(f.endswith(f"mcps/{name}/server.yaml") for f in staged)
            if not hit:
                continue
        text = current_mcp.get(name, "")
        caps_win = _caps_window_for(name, caps)
        in_caps = name in caps or f"mcps/{name}" in caps
        ok, detail = justification_ok(text, caps_win)
        if ok:
            if not in_caps:
                warnings.append(
                    f"MCP {name} justified but missing AIPLAT_CAPABILITIES.md entry"
                )
            continue
        errors.append(
            f"new MCP seed {name!r} beyond baseline — quality proof failed ({detail}). "
            f"Document proof template in server.yaml/CAPABILITIES and/or "
            f"`# ladder-ok: <reason≥15>`; then "
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
