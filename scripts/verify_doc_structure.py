#!/usr/bin/env python3
"""verify_doc_structure.py — 验证 docs/ 目录树与 DOCUMENT_SYSTEM.md 一致性。

Rule: 每次新增 docs/ 子目录时，必须在 DOCUMENT_SYSTEM.md §一 中登记。
未登记的目录 → 阻断（exit code 1）。

Usage:
  python scripts/verify_doc_structure.py          # 全量检查
  python scripts/verify_doc_structure.py --fix    # 自动更新 DOCUMENT_SYSTEM.md（需确认）
"""

import argparse
import os
import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DOCS_DIR = WORKSPACE / "docs"
DOC_SYSTEM = DOCS_DIR / "DOCUMENT_SYSTEM.md"
SCOPE_ROOTS = [
    WORKSPACE / "reports",
    WORKSPACE / "packages",
] + [
    WORKSPACE / name / "docs"
    for name in ("aiPlat-core", "aiPlat-infra", "aiPlat-platform", "aiPlat-management", "aiPlat-app")
]


def get_actual_dirs() -> set:
    """Get all subdirectories under docs/."""
    dirs = set()
    for entry in DOCS_DIR.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            dirs.add(entry.name + "/")
    return dirs


def get_registered_dirs() -> set:
    """Parse DOCUMENT_SYSTEM.md for registered directories."""
    if not DOC_SYSTEM.exists():
        print(f"ERROR: {DOC_SYSTEM} not found")
        sys.exit(1)

    content = DOC_SYSTEM.read_text(encoding="utf-8")
    # Find the tree section between ## 一、目录结构 and the next ## heading
    tree_match = re.search(r"## 一、目录结构.*?(?=^## )", content, re.DOTALL | re.MULTILINE)
    if not tree_match:
        print("ERROR: Could not find directory tree section in DOCUMENT_SYSTEM.md")
        sys.exit(1)

    tree_section = tree_match.group(0)
    dirs = set()
    for line in tree_section.split("\n"):
        # Only match TOP-LEVEL docs/ directories (indentation: 4 spaces + tree char)
        # Pattern: "│   ├── name/"  (4 spaces + ├──)
        m = re.match(r"^│   (?:├──|└──)\s+(\w[\w-]*)/", line)
        if m:
            name = m.group(1)
            if name not in ("docs", "architect", "developer", "ops", "user"):
                dirs.add(name + "/")
    return dirs


def check_scope_roots(strict: bool) -> int:
    """v2.4: root reports/packages/subrepo docs must be registered in DOCUMENT_SYSTEM."""
    content = DOC_SYSTEM.read_text(encoding="utf-8") if DOC_SYSTEM.exists() else ""
    missing = []
    for p in SCOPE_ROOTS:
        if not p.exists():
            continue
        rel = str(p.relative_to(WORKSPACE))
        needle = rel.rstrip("/") + "/"
        if needle not in content and rel not in content:
            missing.append(rel)
    if missing:
        print("⚠️  v2.4 scope 目录未在 DOCUMENT_SYSTEM 登记:")
        for d in missing:
            print(f"   - {d}")
        if strict:
            return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="v2.4 scope 未登记时阻断")
    args = ap.parse_args()
    actual = get_actual_dirs()
    registered = get_registered_dirs()

    unregistered = actual - registered
    missing = registered - actual

    if unregistered:
        print("❌ 以下目录存在于 docs/ 但未在 DOCUMENT_SYSTEM.md 中登记:")
        for d in sorted(unregistered):
            print(f"   - {d}")
        print()
        print(f"修复: 在 {DOC_SYSTEM} §一 中添加这些目录，或运行 --register")

    if missing:
        print("⚠️  以下目录在 DOCUMENT_SYSTEM.md 中登记但 docs/ 中不存在:")
        for d in sorted(missing):
            print(f"   - {d}")

    scope_rc = check_scope_roots(args.strict)
    if unregistered:
        sys.exit(1)
    if scope_rc:
        sys.exit(scope_rc)
    print(f"✅ 全部 {len(actual)} 个目录已在 DOCUMENT_SYSTEM.md 中登记")
    sys.exit(0)


if __name__ == "__main__":
    main()
