#!/usr/bin/env python3
"""verify_document_system.py — DOCUMENT_SYSTEM 自检（Batch 0）。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DOC = WORKSPACE / "docs" / "DOCUMENT_SYSTEM.md"


def fail(msg: str) -> None:
    print(f"❌ {msg}")


def section(text: str, start: str, end: str) -> str:
    m = re.search(rf"{re.escape(start)}.*?(?=^{re.escape(end)})", text, re.S | re.M)
    return m.group(0) if m else ""


def main() -> int:
    errors: list[str] = []
    if not DOC.exists():
        fail(f"missing {DOC}")
        return 1
    text = DOC.read_text(encoding="utf-8")

    # 1. duplicate headings
    headings = re.findall(r"^## (.+)$", text, re.M)
    dup = sorted({h for h in headings if headings.count(h) > 1})
    if dup:
        errors.append("重复章节: " + ", ".join(dup))

    # 2. number table
    sec = section(text, "## 十四、数字声明治理", "## 十五、")
    rows = re.findall(r"^\| (.+?) \| ([\d,]+) \| `(.+)` \|$", sec, re.M)
    if not rows:
        errors.append("十四、数字声明治理：未找到可解析的数字表")
    for name, expected, command in rows:
        try:
            out = subprocess.check_output(command, shell=True, cwd=WORKSPACE, text=True, stderr=subprocess.STDOUT, timeout=30).strip()
        except Exception as exc:
            errors.append(f"{name}: 命令执行失败: {exc}")
            continue
        nums = re.findall(r"\d[\d,]*", out)
        if not nums:
            errors.append(f"{name}: 命令输出无数字: {out[:120]}")
            continue
        actual = int(nums[-1].replace(",", ""))
        exp = int(expected.replace(",", ""))
        if actual != exp:
            errors.append(f"{name}: 当前值 {exp}，命令输出 {actual}")
        print(f"✓ {name}: {actual}")

    # 3. six CLAUDE.md
    claudes = [WORKSPACE / "CLAUDE.md"] + [WORKSPACE / n / "CLAUDE.md" for n in ("aiPlat-core", "aiPlat-infra", "aiPlat-platform", "aiPlat-management", "aiPlat-app")]
    missing = [str(p.relative_to(WORKSPACE)) for p in claudes if not p.exists()]
    if missing:
        errors.append("缺少 CLAUDE.md: " + ", ".join(missing))

    # 4. zombie docs/index.md
    if (WORKSPACE / "docs" / "index.md").exists():
        errors.append("docs/index.md 仍存在；应合并到 docs/README.md")

    # 5. key references
    refs = [
        "docs/README.md",
        "AIPLAT_CAPABILITIES.md",
        "scripts/verify_doc_structure.py",
        "scripts/verify_doc_links.py",
        "docs/archive/README.md",
    ]
    for r in refs:
        if not (WORKSPACE / r).exists():
            errors.append(f"引用不存在: {r}")

    if errors:
        for e in errors:
            fail(e)
        print(f"\n{len(errors)} 项失败")
        return 1
    print("\n✅ DOCUMENT_SYSTEM 自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
