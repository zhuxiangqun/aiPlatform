#!/usr/bin/env python3
"""
Kernel static scan (Phase 2 - 不可绕过)

Purpose:
  Enforce that LLM/Tool/Skill execution is only performed via syscalls, not directly
  from server/agents/loops/graphs/orchestration/mcp.

This script is intentionally simple and dependency-free (no ripgrep required).
It scans *.py under core/ and fails on forbidden call patterns, with allowlists.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Pattern, Tuple


RE_TOOL_EXEC = re.compile(r"\btool\.execute\(")
RE_SKILL_EXEC = re.compile(r"\bskill\.execute\(")
RE_GENERATE = re.compile(r"\.generate\(")
RE_SYS_TOOL = re.compile(r"\bsys_tool_call\(")
RE_SYS_SKILL = re.compile(r"\bsys_skill_call\(")


@dataclass
class Rule:
    name: str
    pattern: Pattern[str]
    allow_prefixes: Tuple[str, ...]
    include_prefixes: Tuple[str, ...] = ()


def _is_allowed(rel_path: str, allow_prefixes: Tuple[str, ...]) -> bool:
    rp = rel_path.replace("\\", "/")
    return any(rp.startswith(p) for p in allow_prefixes)


def _iter_py_files(core_dir: Path) -> Iterable[Path]:
    for p in core_dir.rglob("*.py"):
        # Skip __pycache__ and hidden dirs
        if "__pycache__" in p.parts:
            continue
        yield p


def _scan_file(path: Path, rule: Rule, rel_path: str) -> List[Tuple[int, str]]:
    # If include_prefixes is set, only apply the rule to those paths.
    if rule.include_prefixes:
        rp = rel_path.replace("\\", "/")
        if not any(rp.startswith(p) for p in rule.include_prefixes):
            return []
    if _is_allowed(rel_path, rule.allow_prefixes):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    out: List[Tuple[int, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if rule.pattern.search(line):
            out.append((idx, line.strip()))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    repo_root = Path(__file__).resolve().parents[1]
    core_dir = repo_root / "core"
    if not core_dir.exists():
        print(f"[scan] core dir not found: {core_dir}", file=sys.stderr)
        return 2

    rules = [
        Rule(
            name="forbid tool.execute",
            pattern=RE_TOOL_EXEC,
            allow_prefixes=(
                "core/harness/syscalls/",
                "core/apps/tools/",
                "core/tests/",
            ),
        ),
        Rule(
            name="forbid skill.execute",
            pattern=RE_SKILL_EXEC,
            allow_prefixes=(
                "core/harness/syscalls/",
                "core/apps/skills/",  # skill implementations may call execute internally
                "core/tests/",
            ),
        ),
        Rule(
            name="forbid *.generate (LLM direct call)",
            pattern=RE_GENERATE,
            allow_prefixes=(
                "core/harness/syscalls/",
                "core/adapters/",
                "core/management/adapter_manager.py",
                "core/tests/",
            ),
        ),
        # Orchestrator must be side-effect free: forbid tool/skill syscalls
        Rule(
            name="forbid sys_tool_call in orchestration",
            pattern=RE_SYS_TOOL,
            allow_prefixes=(
                "core/harness/syscalls/",
                "core/tests/",
            ),
            include_prefixes=("core/orchestration/",),
        ),
        Rule(
            name="forbid sys_skill_call in orchestration",
            pattern=RE_SYS_SKILL,
            allow_prefixes=(
                "core/harness/syscalls/",
                "core/tests/",
            ),
            include_prefixes=("core/orchestration/",),
        ),
        # Phase 6: learning package should be side-effect free as well (artifacts only)
        Rule(
            name="forbid sys_tool_call in learning",
            pattern=RE_SYS_TOOL,
            allow_prefixes=("core/harness/syscalls/", "core/tests/"),
            include_prefixes=("core/learning/",),
        ),
        Rule(
            name="forbid sys_skill_call in learning",
            pattern=RE_SYS_SKILL,
            allow_prefixes=("core/harness/syscalls/", "core/tests/"),
            include_prefixes=("core/learning/",),
        ),
    ]

    violations = []
    for f in _iter_py_files(core_dir):
        rel_path = str(f.relative_to(repo_root)).replace("\\", "/")
        for rule in rules:
            hits = _scan_file(f, rule, rel_path)
            for ln, snippet in hits:
                violations.append((rule.name, rel_path, ln, snippet))

    if violations:
        print("[scan] FAILED: forbidden call sites found:\n", file=sys.stderr)
        for name, rel_path, ln, snippet in violations:
            print(f"- {name}: {rel_path}:{ln}: {snippet}", file=sys.stderr)
        print(
            "\n[scan] Fix by routing via syscalls (core/harness/syscalls/*), or adjust allowlist intentionally.",
            file=sys.stderr,
        )
        return 1

    print("[scan] OK: no forbidden call sites found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
