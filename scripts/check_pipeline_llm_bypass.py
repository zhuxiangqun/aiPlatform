#!/usr/bin/env python3
"""check_pipeline_llm_bypass.py — pipeline_engine sys_llm_generate 旁路台账守卫（A2）。

规则：
  1. pipeline_engine.py 内每一处 Call(sys_llm_generate) 必须在调用点上方
     ≤5 行内有注释 ``# bypass-ok: <id>``
  2. <id> 必须出现在 scripts/baselines/pipeline_llm_bypass_allowlist.yaml
  3. allowlist 中多余 id（代码已删）→ WARNING（不阻断），便于清理
  4. disposition=migrate 的命中 → 打印迁移提示（不阻断）；阻断仅针对未登记/未标注

用法：
  python3 scripts/check_pipeline_llm_bypass.py           # 人类可读报告
  python3 scripts/check_pipeline_llm_bypass.py --ci      # 违规退出码 1
  python3 scripts/check_pipeline_llm_bypass.py --inventory
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

WORKSPACE = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = WORKSPACE / "scripts/baselines/pipeline_llm_bypass_allowlist.yaml"
DEFAULT_TARGET = WORKSPACE / "aiPlat-core/core/harness/execution/pipeline_engine.py"
BYPASS_RE = re.compile(r"#\s*bypass-ok:\s*([A-Za-z0-9_.-]+)")


@dataclass
class CallSite:
    lineno: int
    stack: List[str]
    bypass_id: Optional[str]


@dataclass
class AllowEntry:
    id: str
    method: str
    disposition: str
    reason: str


def _load_allowlist(path: Path) -> Tuple[Dict[str, AllowEntry], Path]:
    if yaml is None:
        raise SystemExit("PyYAML required: pip install pyyaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    target = WORKSPACE / str(data.get("file") or DEFAULT_TARGET.relative_to(WORKSPACE))
    entries: Dict[str, AllowEntry] = {}
    for raw in data.get("entries") or []:
        eid = str(raw["id"]).strip()
        entries[eid] = AllowEntry(
            id=eid,
            method=str(raw.get("method") or ""),
            disposition=str(raw.get("disposition") or "keep"),
            reason=str(raw.get("reason") or ""),
        )
    return entries, target


def _find_bypass_id(lines: List[str], lineno: int, lookback: int = 5) -> Optional[str]:
    # lineno is 1-based
    start = max(0, lineno - 1 - lookback)
    end = lineno  # inclusive of the call line itself
    for i in range(end - 1, start - 1, -1):
        m = BYPASS_RE.search(lines[i])
        if m:
            return m.group(1)
    return None


def _collect_calls(src: str) -> List[CallSite]:
    tree = ast.parse(src)
    lines = src.splitlines()
    sites: List[CallSite] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: List[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # type: ignore[override]
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

        def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name == "sys_llm_generate":
                sites.append(
                    CallSite(
                        lineno=node.lineno,
                        stack=list(self.stack),
                        bypass_id=_find_bypass_id(lines, node.lineno),
                    )
                )
            self.generic_visit(node)

    Visitor().visit(tree)
    return sites


def check(
    allowlist: Dict[str, AllowEntry],
    target: Path,
) -> Tuple[List[str], List[str], List[CallSite]]:
    """Returns (violations, warnings, sites)."""
    src = target.read_text(encoding="utf-8")
    sites = _collect_calls(src)
    violations: List[str] = []
    warnings: List[str] = []
    used_ids = set()

    for site in sites:
        leaf = site.stack[-1] if site.stack else "<module>"
        if not site.bypass_id:
            violations.append(
                f"L{site.lineno} in {leaf}(): missing `# bypass-ok: <id>` "
                f"(CLAUDE.md §8b / A2 allowlist)"
            )
            continue
        used_ids.add(site.bypass_id)
        entry = allowlist.get(site.bypass_id)
        if entry is None:
            violations.append(
                f"L{site.lineno} in {leaf}(): bypass-ok id {site.bypass_id!r} "
                f"not in {ALLOWLIST_PATH.relative_to(WORKSPACE)}"
            )
            continue
        if entry.method and entry.method not in site.stack and entry.method != leaf:
            warnings.append(
                f"L{site.lineno}: id={site.bypass_id} expected method "
                f"{entry.method!r}, stack={site.stack}"
            )
        if entry.disposition == "migrate":
            warnings.append(
                f"L{site.lineno}: id={site.bypass_id} disposition=migrate — {entry.reason}"
            )

    for eid, entry in allowlist.items():
        if eid not in used_ids:
            warnings.append(
                f"allowlist stale: id={eid!r} ({entry.disposition}) not found in {target.name}"
            )

    return violations, warnings, sites


def _print_inventory(sites: List[CallSite], allowlist: Dict[str, AllowEntry]) -> None:
    print(f"{'LINE':>6}  {'ID':<28}  {'DISP':<12}  METHOD STACK")
    print("-" * 88)
    for site in sites:
        eid = site.bypass_id or "?"
        disp = allowlist[eid].disposition if eid in allowlist else "UNLISTED"
        stack = "/".join(site.stack) or "<module>"
        print(f"{site.lineno:>6}  {eid:<28}  {disp:<12}  {stack}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ci", action="store_true", help="exit 1 on violations")
    ap.add_argument("--inventory", action="store_true", help="print call-site table")
    ap.add_argument(
        "--allowlist",
        type=Path,
        default=ALLOWLIST_PATH,
        help="path to allowlist YAML",
    )
    args = ap.parse_args(argv)

    allowlist, target = _load_allowlist(args.allowlist)
    if not target.is_file():
        print(f"FAIL: target missing: {target}", file=sys.stderr)
        return 1

    violations, warnings, sites = check(allowlist, target)

    if args.inventory or not args.ci:
        _print_inventory(sites, allowlist)
        print()

    for w in warnings:
        print(f"WARN: {w}")
    for v in violations:
        print(f"FAIL: {v}")

    print(
        f"summary: calls={len(sites)} allowlist={len(allowlist)} "
        f"violations={len(violations)} warnings={len(warnings)}"
    )

    if violations:
        if args.ci:
            return 1
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
