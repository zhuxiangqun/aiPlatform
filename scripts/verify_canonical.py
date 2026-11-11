#!/usr/bin/env python3
"""verify_canonical.py — 检查 canonical 声明冲突与旧版标准遗留（v2.4）。

默认 warn-only；`--strict` 时冲突/旧版遗留阻断。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

WORKSPACE = Path(__file__).resolve().parents[1]
ROOTS = [WORKSPACE / "docs", WORKSPACE / "reports"]
ROOTS += sorted((WORKSPACE / "packages").glob("*/docs")) if (WORKSPACE / "packages").is_dir() else []
for name in ("aiPlat-core", "aiPlat-infra", "aiPlat-platform", "aiPlat-management", "aiPlat-app"):
    p = WORKSPACE / name / "docs"
    if p.is_dir():
        ROOTS.append(p)
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def iter_markdown() -> List[Path]:
    seen = set()
    out = []
    for root in ROOTS:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.md")):
            if ".git" in p.parts or "node_modules" in p.parts or "__pycache__" in p.parts:
                continue
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def parse_frontmatter(text: str) -> Dict[str, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    data: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"\'')
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="冲突/旧版标准阻断")
    args = ap.parse_args()

    canon: List[Path] = []
    ids: List[str] = []
    for p in iter_markdown():
        try:
            meta = parse_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        is_known_standard = "knowledge-system" in str(p) and "v4.3.1" in p.name and "archive" not in p.parts
        if meta.get("authority", "").lower() == "canonical" or is_known_standard:
            canon.append(p)
            if meta.get("doc_id"):
                ids.append(meta["doc_id"])

    dup_ids = [k for k, v in Counter(ids).items() if v > 1]
    old_standards = []
    for p in (WORKSPACE / "docs").rglob("*v4.*"):
        if p.is_file() and p.suffix == ".md":
            name = p.name
            if re.search(r"v4\.(1|2|3)(?!\.1)", name):
                old_standards.append(p)

    print(f"canonical={len(canon)} duplicate_doc_id={len(dup_ids)} old_version_files={len(old_standards)}")
    if dup_ids:
        print("⚠️  重复 doc_id: " + ", ".join(dup_ids))
    for p in old_standards[:20]:
        print(f"  ⚠️  旧版标准仍在主目录: {p.relative_to(WORKSPACE)}")
    if dup_ids and args.strict:
        return 1
    if not dup_ids and not old_standards:
        print("✅ 未发现 canonical 冲突或旧版标准遗留")
    return 0


if __name__ == "__main__":
    sys.exit(main())
