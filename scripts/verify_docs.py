#!/usr/bin/env python3
"""
aiPlat 文档系统治理验证脚本

验证规则（基于 docs/DOCUMENT_SYSTEM.md）：
1. (阻断) docs/by-role/ 下所有 .md 文件的相对链接必须可解析
2. (阻断) docs/reports/ 下所有 .md 必须包含"不手动编辑"头部声明
3. (阻断) docs/archive/README.md 必须包含"仅做历史参考"免责声明
4. (告警) AIPLAT_CAPABILITIES.md 以外的文件不应硬编码当前能力数
5. (告警) 检测是否存在重复的"唯一真相源"声明

退出码：
  0: 全部通过（仅有告警）
  1: 阻断性错误
"""

import os
import re
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).parent.parent.absolute()
DOCS_ROOT = REPO_ROOT / "docs"
ROLE_DIR = DOCS_ROOT / "by-role"
REPORTS_DIR = DOCS_ROOT / "reports"
ARCHIVE_README = DOCS_ROOT / "archive" / "README.md"
CAPABILITIES_FILE = REPO_ROOT / "AIPLAT_CAPABILITIES.md"

errors: List[str] = []
warnings: List[str] = []


def log_error(msg: str) -> None:
    errors.append(f"\u274c {msg}")
    print(f"[ERROR] {msg}")


def log_warning(msg: str) -> None:
    warnings.append(f"\u26a0\ufe0f {msg}")
    print(f"[WARN] {msg}")


# ── 检查 1：by-role 链接有效性（阻断） ──
def check_role_links() -> None:
    if not ROLE_DIR.exists():
        log_warning(f"by-role 目录不存在: {ROLE_DIR}")
        return

    md_files = list(ROLE_DIR.glob("**/*.md"))
    if not md_files:
        log_warning(f"by-role/ 下无 .md 文件")
        return

    link_pattern = re.compile(r'\[.*?\]\((?!https?://)([^)]+)\)')

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        rel_dir = md_file.parent

        for match in link_pattern.finditer(content):
            raw_path = match.group(1)
            if '#' in raw_path:
                target_path = raw_path.split('#')[0]
            else:
                target_path = raw_path

            if not target_path:
                continue

            abs_target = (rel_dir / target_path).resolve()
            try:
                abs_target.relative_to(REPO_ROOT)
            except ValueError:
                log_error(f"{md_file.relative_to(REPO_ROOT)} 链接指向仓库外: {raw_path}")
                continue

            if not abs_target.exists():
                log_error(f"{md_file.relative_to(REPO_ROOT)} 链接损坏: {raw_path}")


# ── 检查 2：报告头部声明（阻断） ──
def check_report_headers() -> None:
    if not REPORTS_DIR.exists():
        log_warning(f"reports 目录不存在: {REPORTS_DIR}")
        return

    md_files = list(REPORTS_DIR.glob("*.md"))
    if not md_files:
        return

    required = ["不手动编辑", "生成时间"]
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        found = all(phrase in content for phrase in required)
        if not found:
            log_error(f"{md_file.relative_to(REPO_ROOT)} 缺少报告头部声明（须包含: {required}）")


# ── 检查 3：归档免责声明（阻断） ──
def check_archive_disclaimer() -> None:
    if not ARCHIVE_README.exists():
        log_error(f"归档说明文件缺失: {ARCHIVE_README.relative_to(REPO_ROOT)}")
        return

    content = ARCHIVE_README.read_text(encoding="utf-8")
    if "\u4ec5\u505a\u5386\u53f2\u53c2\u8003" not in content:
        log_error(f"{ARCHIVE_README.relative_to(REPO_ROOT)} 必须包含 \"\u4ec5\u505a\u5386\u53f2\u53c2\u8003\" 声明")


# ── 检查 4：数字硬编码（告警） ──
def check_hardcoded_numbers() -> None:
    if not CAPABILITIES_FILE.exists():
        log_warning("能力清单文件不存在，跳过硬编码检查")
        return

    content = CAPABILITIES_FILE.read_text(encoding="utf-8")
    current_count = content.count("\u2705")
    if current_count == 0:
        log_warning("能力清单中未检测到 \u2705 标记")
        return

    all_md = list(REPO_ROOT.glob("**/*.md"))
    excluded = {CAPABILITIES_FILE.resolve()}
    target_files = [f for f in all_md if f.resolve() not in excluded]

    pattern = re.compile(rf'\b{current_count}\b')
    for md_file in target_files:
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if not pattern.search(text):
            continue

        lines = text.splitlines()
        for line in lines:
            if pattern.search(line):
                if "CAPABILITIES" not in line and "\u51fa\u5904" not in line and "\u5f15\u7528" not in line:
                    rel = md_file.relative_to(REPO_ROOT)
                    log_warning(f"{rel} 中裸写了数字 {current_count}，应引用 CAPABILITIES.md 而非硬编码")
                    break


# ── 检查 5：重复的"唯一真相源"声明（告警） ──
def check_duplicate_authority() -> None:
    if not DOCS_ROOT.exists():
        return

    patterns = [r"\u552f\u4e00\u771f\u76f8\u6e90", r"\u552f\u4e00\u51fa\u5904",
                r"single source of truth"]
    combined = re.compile('|'.join(patterns), re.IGNORECASE)

    allowed = {
        DOCS_ROOT / "DOCUMENT_SYSTEM.md",
        DOCS_ROOT / "architecture" / "overview.md",
        REPO_ROOT / "AIPLAT_CAPABILITIES.md",
    }

    md_files = list(DOCS_ROOT.glob("**/*.md"))
    for md_file in md_files:
        if md_file.resolve() in {p.resolve() for p in allowed}:
            continue
        if "archive" in md_file.parts:
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if combined.search(text):
            rel = md_file.relative_to(REPO_ROOT)
            log_warning(f"{rel} 中出现了\"唯一真相源\"类声明，未被列入权威白名单")


def main():
    print(f"\U0001f50d 文档系统验证开始 (REPO_ROOT: {REPO_ROOT})")
    print("=" * 60)

    check_role_links()
    check_report_headers()
    check_archive_disclaimer()
    check_hardcoded_numbers()
    check_duplicate_authority()

    print("=" * 60)
    if errors:
        print(f"\u274c 阻断性错误: {len(errors)} 个")
        for e in errors:
            print(f"  {e}")
        print(f"\u26a0\ufe0f 告警: {len(warnings)} 个（不阻断）")
        sys.exit(1)
    elif warnings:
        print(f"\u26a0\ufe0f 告警: {len(warnings)} 个（不阻断）")
        for w in warnings:
            print(f"  {w}")
        with open(os.environ.get('GITHUB_OUTPUT', '/dev/null'), 'a') as f:
            f.write(f"warnings={chr(10).join(warnings)}\n")
        sys.exit(0)
    else:
        print("\u2705 所有验证通过！文档系统健康。")
        sys.exit(0)


if __name__ == "__main__":
    main()
