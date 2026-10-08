#!/usr/bin/env python3
"""check_retrieval_entrypoints.py — W4: user-facing Q&A must use CRAG.

Rules:
  - Platform routers / kb intelligence / agents that call ``kb_retrieve`` or
    ``sys_kb_retrieve`` for Q&A must instead use ``kb_qa_retrieve`` /
    ``sys_crag_retrieve`` (GraphRAG is L0 inside CRAG, not a separate user API).
  - Low-level building blocks are allowlisted (CRAG itself, facades, syscalls).

Usage:
  python3 scripts/check_retrieval_entrypoints.py
  python3 scripts/check_retrieval_entrypoints.py --ci
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

WORKSPACE = Path(__file__).resolve().parents[1]

# Paths (relative) where raw kb_retrieve / sys_kb_retrieve is legitimate
ALLOW_PREFIXES = (
    "aiPlat-core/core/harness/syscalls/",
    "aiPlat-core/core/api/facades/kb_facade.py",
    "aiPlat-core/core/api/core_facade.py",
    "aiPlat-core/core/harness/knowledge/",
    "aiPlat-core/core/harness/knowledge_pipeline/",
    "aiPlat-core/core/apps/tools/",
    "aiPlat-core/core/tests/",
    "tests/",
)

# User-facing surfaces that MUST NOT call raw retrieve for Q&A
SCAN_GLOBS = [
    "aiPlat-platform/api/routers/**/*.py",
    "aiPlat-platform/kb/intelligence/**/*.py",
    "aiPlat-core/core/apps/agents/**/*.py",
]

BAD_RE = re.compile(
    r"\b(kb_retrieve|sys_kb_retrieve)\s*\("
)
# Exempt if same file clearly uses CRAG for the Q&A path and this is a comment
COMMENT_RE = re.compile(r"^\s*#")


def _allowed(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    for p in ALLOW_PREFIXES:
        if rel == p.rstrip("/") or rel.startswith(p):
            return True
    return False


def _scan_file(path: Path) -> List[str]:
    try:
        rel = str(path.relative_to(WORKSPACE)).replace("\\", "/")
    except ValueError:
        rel = str(path)
    if _allowed(rel):
        return []
    violations: List[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    # Flag direct kb_retrieve calls; lines that already invoke CRAG are skipped
    for i, line in enumerate(lines, 1):
        if COMMENT_RE.match(line):
            continue
        if "kb_qa_retrieve" in line or "sys_crag_retrieve" in line:
            continue
        m = BAD_RE.search(line)
        if m:
            violations.append(
                f"{rel}:{i}: raw {m.group(1)}() — use kb_qa_retrieve / sys_crag_retrieve (W4)"
            )
    return violations


def check() -> Tuple[List[str], int]:
    files: List[Path] = []
    for pattern in SCAN_GLOBS:
        files.extend(WORKSPACE.glob(pattern))
    files = sorted({f for f in files if f.is_file() and f.suffix == ".py"})
    violations: List[str] = []
    for f in files:
        violations.extend(_scan_file(f))
    return violations, len(files)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ci", action="store_true")
    args = ap.parse_args(argv)
    violations, n = check()
    for v in violations:
        print(f"FAIL: {v}")
    print(f"summary: files={n} violations={len(violations)}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
