#!/usr/bin/env python3
"""verify_doc_links.py — 验证文档中的 Markdown 文件链接是否有效。

检查范围（E2 · 2026-10）：
  fail：
    - docs/DOCUMENT_SYSTEM.md
    - docs/**/README.md（路径不含 archive / _archive）
    - reports/docs-governance/README.md
    - docs/README.md 已链到的维护区文件（入口一层，仍非全站）
  warn：
    - docs/**/README.md 且路径含 archive / _archive

解析：相对文件目录 → workspace root → 各子仓根。

Usage:
  python3 scripts/verify_doc_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DOCS_DIR = WORKSPACE / "docs"
REPO_DIRS = [
    WORKSPACE / "aiPlat-core",
    WORKSPACE / "aiPlat-infra",
    WORKSPACE / "aiPlat-platform",
    WORKSPACE / "aiPlat-management",
    WORKSPACE / "aiPlat-app",
]

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _is_archive_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return "archive" in parts or "_archive" in parts


def extract_md_links(content: str) -> list[tuple[int, str]]:
    """Extract [text](path) Markdown links (skip http/mailto/#)."""
    links: list[tuple[int, str]] = []
    for m in MD_LINK_RE.finditer(content):
        path = m.group(2).strip()
        if path.startswith(("http://", "https://", "#", "mailto:")):
            continue
        links.append((m.start(), path))
    return links


def resolve_path(base_dir: Path, link: str) -> Path | None:
    """Resolve a relative link against a base directory."""
    if "#" in link:
        link = link.split("#", 1)[0]
    if not link:
        return None
    return (base_dir / link).resolve()


def link_exists(filepath: Path, link: str) -> bool:
    rel_resolved = resolve_path(filepath.parent, link)
    if rel_resolved and rel_resolved.exists():
        return True
    ws_resolved = resolve_path(WORKSPACE, link)
    if ws_resolved and ws_resolved.exists():
        return True
    for repo_dir in REPO_DIRS:
        repo_resolved = resolve_path(repo_dir, link)
        if repo_resolved and repo_resolved.exists():
            return True
    return False


def check_file(filepath: Path, *, severity: str = "fail", print_cap: int = 10) -> int:
    """Check all links in a file. Returns count of broken links."""
    if not filepath.exists():
        label = "❌" if severity == "fail" else "⚠️"
        print(f"  {label} 文件本身不存在: {filepath}")
        return 1

    content = filepath.read_text(encoding="utf-8", errors="ignore")
    links = extract_md_links(content)
    errors = 0
    icon = "❌" if severity == "fail" else "⚠️"

    for pos, link in links:
        if link_exists(filepath, link):
            continue
        errors += 1
        if errors <= print_cap:
            line_num = content[:pos].count("\n") + 1
            short = filepath.relative_to(WORKSPACE) if filepath.is_relative_to(WORKSPACE) else filepath
            print(f"  {icon} {short}:{line_num} → {link}")

    if errors > print_cap:
        print(f"  ... and {errors - print_cap} more broken links in {filepath.name}")
    return errors


def collect_maint_readmes() -> list[Path]:
    """docs/**/README.md excluding archive/_archive path segments."""
    if not DOCS_DIR.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(DOCS_DIR.rglob("README.md")):
        if _is_archive_path(p):
            continue
        out.append(p)
    return out


def collect_archive_readmes() -> list[Path]:
    if not DOCS_DIR.is_dir():
        return []
    return sorted(p for p in DOCS_DIR.rglob("README.md") if _is_archive_path(p))


def collect_docs_readme_one_hop(docs_readme: Path) -> list[Path]:
    """Maint-area .md/.mdx targets linked from docs/README.md (one hop)."""
    if not docs_readme.exists():
        return []
    content = docs_readme.read_text(encoding="utf-8", errors="ignore")
    targets: list[Path] = []
    seen: set[Path] = set()
    for _, link in extract_md_links(content):
        for base in (docs_readme.parent, WORKSPACE):
            resolved = resolve_path(base, link)
            if not resolved or not resolved.exists():
                continue
            if not resolved.is_file():
                break
            if resolved.suffix.lower() not in {".md", ".mdx"}:
                break
            try:
                resolved.relative_to(DOCS_DIR)
            except ValueError:
                break
            if _is_archive_path(resolved):
                break
            if resolved not in seen:
                seen.add(resolved)
                targets.append(resolved)
            break
    return targets


def build_fail_set() -> list[Path]:
    """Ordered unique fail-severity files."""
    ordered: list[Path] = []
    seen: set[Path] = set()

    def add(p: Path) -> None:
        rp = p.resolve()
        if rp in seen or not p.exists():
            return
        seen.add(rp)
        ordered.append(p)

    add(DOCS_DIR / "DOCUMENT_SYSTEM.md")
    for p in collect_maint_readmes():
        add(p)
    add(WORKSPACE / "reports" / "docs-governance" / "README.md")
    docs_readme = DOCS_DIR / "README.md"
    for p in collect_docs_readme_one_hop(docs_readme):
        # Skip READMEs already covered; still include other maint .md
        add(p)
    return ordered


def main() -> None:
    fail_files = build_fail_set()
    warn_files = collect_archive_readmes()

    total_fail = 0
    for f in fail_files:
        short = str(f.relative_to(WORKSPACE))
        errors = check_file(f, severity="fail")
        if errors:
            print(f"  {short}: {errors} broken links (fail)")
        total_fail += errors

    total_warn = 0
    for f in warn_files:
        short = str(f.relative_to(WORKSPACE))
        errors = check_file(f, severity="warn")
        if errors:
            print(f"  {short}: {errors} broken links (warn)")
        total_warn += errors

    print(
        f"\nChecked fail={len(fail_files)} warn={len(warn_files)} "
        f"| broken fail={total_fail} warn={total_warn}"
    )
    if total_fail:
        print(f"❌ {total_fail} broken maint/入口 links")
        sys.exit(1)
    if total_warn:
        print(f"⚠️  {total_warn} broken archive links (warn only)")
    print("✅ All fail-scope links valid")
    sys.exit(0)


if __name__ == "__main__":
    main()
