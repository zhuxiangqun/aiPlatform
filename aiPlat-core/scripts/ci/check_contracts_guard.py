#!/usr/bin/env python3
"""
ClaudeCode 风格“强约束”守护脚本：

1) links：检查 docs/contracts 下 markdown 的本地链接是否存在
2) binding：如果 contracts 变更，则必须同步更新验收（tests 或 06-acceptance-contract.md）
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


RE_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _repo_root() -> Path:
    # script: aiPlat-core/scripts/ci/check_contracts_guard.py
    return Path(__file__).resolve().parents[3]


def _run(cmd: list[str]) -> str:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout or "").strip())
    return (cp.stdout or "").strip()


def _iter_contract_md_files(repo_root: Path) -> list[Path]:
    base = repo_root / "aiPlat-core" / "docs" / "contracts"
    if not base.exists():
        return []
    return sorted([p for p in base.rglob("*.md") if p.is_file()])


def cmd_links(repo_root: Path) -> int:
    files = _iter_contract_md_files(repo_root)
    if not files:
        print("contracts: no files found, skip")
        return 0

    bad: list[str] = []
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        for raw in RE_MD_LINK.findall(text):
            url = raw.strip()
            if not url:
                continue
            # ignore external/anchors/templates
            if url.startswith(("http://", "https://", "mailto:")):
                continue
            if url.startswith("#"):
                continue
            if "{{" in url or "}}" in url:
                continue
            # strip title: (path "title")
            url = url.split(" ", 1)[0].strip()
            url = url.split("#", 1)[0].strip()
            if not url:
                continue

            target = (p.parent / url).resolve()
            # keep within repo
            try:
                target.relative_to(repo_root)
            except Exception:
                bad.append(f"{p.relative_to(repo_root)}: link escapes repo: {raw}")
                continue
            if not target.exists():
                bad.append(f"{p.relative_to(repo_root)}: missing link target: {raw}")

    if bad:
        print("contracts: link check failed:")
        for b in bad:
            print(" -", b)
        return 1

    print(f"contracts: link check ok ({len(files)} files)")
    return 0


def cmd_binding(repo_root: Path, base: str, head: str) -> int:
    if not base or not head:
        print("contracts: binding check requires --base/--head")
        return 2

    # GitHub Actions 已 checkout 并 fetch-depth=0
    diff = _run(["git", "diff", "--name-only", f"{base}..{head}"])
    changed = [l.strip() for l in (diff or "").splitlines() if l.strip()]
    if not changed:
        print("contracts: no changed files, skip")
        return 0

    contracts_prefix = "aiPlat-core/docs/contracts/"
    tests_prefix = "aiPlat-core/core/tests/"
    acceptance_doc = "aiPlat-core/docs/contracts/06-acceptance-contract.md"

    contracts_changed = [p for p in changed if p.startswith(contracts_prefix)]
    if not contracts_changed:
        print("contracts: no contracts changes, ok")
        return 0

    tests_changed = any(p.startswith(tests_prefix) for p in changed)
    acceptance_changed = acceptance_doc in changed

    if not (tests_changed or acceptance_changed):
        print("contracts: contracts changed but acceptance not updated.")
        print("MUST: update tests under aiPlat-core/core/tests/ OR update 06-acceptance-contract.md")
        print("Changed contracts files:")
        for p in contracts_changed:
            print(" -", p)
        return 1

    print("contracts: binding ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("links")

    p_bind = sub.add_parser("binding")
    p_bind.add_argument("--base", required=True)
    p_bind.add_argument("--head", required=True)

    args = parser.parse_args()
    repo_root = _repo_root()

    if args.cmd == "links":
        return cmd_links(repo_root)
    if args.cmd == "binding":
        return cmd_binding(repo_root, base=str(args.base), head=str(args.head))

    return 2


if __name__ == "__main__":
    sys.exit(main())

