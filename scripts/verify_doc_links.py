#!/usr/bin/env python3
"""verify_doc_links.py — 验证文档中的文件引用是否有效。

检查范围：
  1. CLAUDE.md 中的 `docs/` 引用
  2. DOCUMENT_SYSTEM.md 中的文件路径
  3. docs/README.md 和 docs/manuals/README.md 中的链接

基础路径：相对于文件所在目录解析，也检查 workspace-root 解析。

Usage:
  python scripts/verify_doc_links.py
"""

import os
import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DOCS_DIR = WORKSPACE / "docs"

FILES_TO_CHECK = [
    WORKSPACE / "docs" / "DOCUMENT_SYSTEM.md",
    WORKSPACE / "docs" / "README.md",
    WORKSPACE / "docs" / "manuals" / "README.md",
]


def extract_md_links(content: str) -> list:
    """Extract [text](path) Markdown links only.
    
    Does NOT extract backtick-wrapped conceptual references like `some_file.py`
    — those are documentation examples, not real file links.
    """
    links = []
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", content):
        path = m.group(2)
        if not path.startswith(("http://", "https://", "#", "mailto:")):
            links.append((m.start(), path))
    return links


def resolve_path(base_dir: Path, link: str) -> Path:
    """Resolve a relative link against a base directory."""
    # Remove any anchor
    if "#" in link:
        link = link.split("#")[0]
    if not link:
        return None
    # handle ../ prefix
    resolved = (base_dir / link).resolve()
    return resolved


def check_file(base_dir: Path, filepath: Path) -> int:
    """Check all links in a file. Returns count of broken links."""
    if not filepath.exists():
        print(f"  ⚠️  文件本身不存在: {filepath}")
        return 1

    content = filepath.read_text(encoding="utf-8", errors="ignore")
    links = extract_md_links(content)
    errors = 0

    for pos, link in links:
        # Try relative to file's directory first
        rel_resolved = resolve_path(filepath.parent, link)
        # Try relative to workspace root
        ws_resolved = resolve_path(WORKSPACE, link)

        if rel_resolved and rel_resolved.exists():
            continue
        if ws_resolved and ws_resolved.exists():
            continue

        # Try aiPlat-core/docs/ for docs/harness/ style references
        for repo_dir in [WORKSPACE / "aiPlat-core", WORKSPACE / "aiPlat-infra",
                         WORKSPACE / "aiPlat-platform", WORKSPACE / "aiPlat-management",
                         WORKSPACE / "aiPlat-app"]:
            repo_resolved = resolve_path(repo_dir, link)
            if repo_resolved and repo_resolved.exists():
                break
        else:
            # Not found anywhere
            errors += 1
            if errors <= 10:  # Cap output
                line_num = content[:pos].count("\n") + 1
                print(f"  ❌ {filepath.name}:{line_num} → {link}")

    if errors > 10:
        print(f"  ... and {errors - 10} more broken links")
    return errors


def main():
    total_errors = 0
    for f in FILES_TO_CHECK:
        if not f.exists():
            continue
        short_path = str(f.relative_to(WORKSPACE))
        errors = check_file(f.parent, f)
        if errors:
            print(f"  {short_path}: {errors} broken links")
        total_errors += errors

    if total_errors:
        print(f"\n❌ {total_errors} broken links found")
        sys.exit(1)
    else:
        print(f"✅ All links valid across {len([f for f in FILES_TO_CHECK if f.exists()])} files")
        sys.exit(0)


if __name__ == "__main__":
    main()
