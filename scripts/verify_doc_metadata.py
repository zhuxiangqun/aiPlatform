#!/usr/bin/env python3
"""verify_doc_metadata.py — 检查文档元数据（v2.4）。

默认 warn-only；`--strict` 时 canonical 文档缺字段才阻断。
检查范围：docs/、reports/、packages/*/docs/、aiPlat-*/docs/。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

WORKSPACE = Path(__file__).resolve().parents[1]
ROOTS = [WORKSPACE / "docs", WORKSPACE / "reports"]
ROOTS += sorted((WORKSPACE / "packages").glob("*/docs")) if (WORKSPACE / "packages").is_dir() else []
for name in ("aiPlat-core", "aiPlat-infra", "aiPlat-platform", "aiPlat-management", "aiPlat-app"):
    p = WORKSPACE / name / "docs"
    if p.is_dir():
        ROOTS.append(p)

REQUIRED_CANONICAL = ("doc_id", "doc_type", "status", "authority", "purpose", "scope_in", "scope_out", "owner", "version")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def iter_markdown() -> List[Path]:
    """iter_markdown。
    """
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
    """parse_frontmatter。

    Args:
        text: text 参数。
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    data: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"\'')
    return data


def main() -> int:
    """main。
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="canonical 缺字段时阻断")
    args = ap.parse_args()

    files = iter_markdown()
    total = len(files)
    canonical = 0
    missing: List[Tuple[Path, List[str]]] = []
    with_meta = 0
    missing_type: List[Path] = []
    invalid_type: List[Tuple[Path, str]] = []
    valid_types = {"Standard", "Architecture", "Contract", "Product", "Guide", "Runbook", "Reference", "Report", "Decision", "Index", "Agent Instruction", "Archive", "Draft"}

    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        meta = parse_frontmatter(text)
        if meta:
            with_meta += 1
        dt = meta.get("doc_type", "").strip()
        if not dt:
            missing_type.append(p)
        elif dt not in valid_types:
            invalid_type.append((p, dt))
        is_known_standard = (
            p.name in ("technical-whitepaper.md", "normative-appendix.md",
                       "aiplat-knowledge-system-technical-whitepaper-v4.3.1-2026-11-11.md",
                       "aiplat-knowledge-system-engineering-appendix-v4.3.1-2026-11-11.md")
            and "knowledge-system" in str(p)
            and "archive" not in p.parts
        )
        if meta.get("authority", "").lower() != "canonical" and not is_known_standard:
            continue
        canonical += 1
        if is_known_standard:
            # 标准包由 manifest/approval record 治理，正文不重复 frontmatter
            continue
        gaps = [k for k in REQUIRED_CANONICAL if not meta.get(k)]
        if gaps:
            missing.append((p, gaps))

    print(f"scanned={total} with_frontmatter={with_meta} canonical={canonical}")
    if missing_type:
        print(f"⚠️  缺 doc_type: {len(missing_type)}")
        for p in missing_type[:20]:
            print(f"  - {p.relative_to(WORKSPACE)}")
    if invalid_type:
        print(f"⚠️  非法 doc_type: {len(invalid_type)}")
        for p, dt in invalid_type[:20]:
            print(f"  - {p.relative_to(WORKSPACE)}: {dt}")
    if missing:
        print(f"⚠️  canonical 文档缺字段: {len(missing)}")
        for p, gaps in missing[:20]:
            print(f"  - {p.relative_to(WORKSPACE)}: 缺 {', '.join(gaps)}")
    if args.strict and (missing or missing_type or invalid_type):
        return 1
    if not (missing or missing_type or invalid_type):
        print("✅ 全部文档 doc_type 有效，canonical 元数据完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
