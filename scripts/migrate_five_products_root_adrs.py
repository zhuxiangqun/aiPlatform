#!/usr/bin/env python3
"""Migrate reports/five-products/*.md out of the flat root (DOCUMENT_SYSTEM §11.1).

Destinations:
  - decisions + drafts → docs/decisions/products/five-products/
  - program/status/ops narrative → reports/products/five-products/program/

Leaves Index stubs at the old paths. Rewrites repo-root string refs and
depth-adjusted relative links inside moved files.

Does not Accept ADRs or flip authorize flags.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "reports" / "five-products"
DEC = ROOT / "docs" / "decisions" / "products" / "five-products"
PROG = ROOT / "reports" / "products" / "five-products" / "program"

# Old depth reports/five-products = 2; new depths = 4 → relative ../ gains +2.
_REL_UP_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])(\.\./)(packages/|aiPlat-|docs/|reports/|scripts/)"
)


def _is_draft(name: str) -> bool:
    low = name.lower()
    return "draft" in low or name.startswith("ADR-DRAFT")


def _is_decision(name: str) -> bool:
    if _is_draft(name):
        return True  # drafts travel with decisions (same dir, keep ./ links)
    if name.startswith("ADR"):
        return True
    if name.startswith("GATE") and (
        "DECISION" in name or name in {"GATE1_PACKAGE.md", "GATE2_RECOMMENDATION.md"}
    ):
        return True
    if name.endswith("_DECISION.md"):
        return True
    return name in {
        "DECISIONS_AND_AUTHORIZATIONS.md",
        "L1_AUTHORIZATION.md",
        "GATE1_PACKAGE.md",
        "GATE2_RECOMMENDATION.md",
    }


def _git_mv(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(["git", "mv", str(src), str(dst)], cwd=ROOT)


def _stub(old: Path, new_rel: str) -> None:
    name = old.name
    body = "\n".join(
        [
            "---",
            "doc_type: Index",
            "status: active",
            "authority: supporting",
            f"doc_id: STUB_FP_{re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_').upper()[:40]}",
            "last_reviewed: 2026-11-15",
            "---",
            "",
            f"# {name}（已迁移）",
            "",
            f"> 正文已迁至 [`{new_rel}`]({new_rel})。",
            "",
            "本页保留为旧路径 Index stub，避免历史链接与脚本硬编码断链。",
            "",
        ]
    )
    old.write_text(body + "\n", encoding="utf-8")
    subprocess.check_call(["git", "add", str(old)], cwd=ROOT)


def _rewrite_moved_relative(text: str) -> str:
    """Bump ../ for repo-root targets when file depth increases by 2."""

    def repl(m: re.Match[str]) -> str:
        # Prepend two additional ../ segments (depth 2 → 4).
        return "../../" + m.group(0)

    return _REL_UP_RE.sub(repl, text)


def _rewrite_repo_refs(text: str, mapping: dict[str, str]) -> str:
    out = text
    # Longest keys first
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        out = out.replace(old, new)
    return out


def main() -> int:
    """执行五产品根级 ADR/程序叙事迁移并改写仓库内路径引用。

    Returns:
        进程退出码：0 成功，非 0 失败。
    """
    if not SRC.is_dir():
        print("FAIL missing", SRC, file=sys.stderr)
        return 1

    mds = sorted(SRC.glob("*.md"))
    # Exclude stubs already present for ops/contracts (none at root *.md)
    decisions: list[Path] = []
    program: list[Path] = []
    for p in mds:
        if _is_decision(p.name):
            decisions.append(p)
        else:
            program.append(p)

    DEC.mkdir(parents=True, exist_ok=True)
    PROG.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    moved: list[tuple[Path, Path, str]] = []

    for p in decisions:
        dst = DEC / p.name
        if dst.exists():
            print("FAIL exists", dst, file=sys.stderr)
            return 1
        _git_mv(p, dst)
        new_rel = f"docs/decisions/products/five-products/{p.name}"
        mapping[f"reports/five-products/{p.name}"] = new_rel
        moved.append((p, dst, new_rel))

    for p in program:
        dst = PROG / p.name
        if dst.exists():
            print("FAIL exists", dst, file=sys.stderr)
            return 1
        _git_mv(p, dst)
        new_rel = f"reports/products/five-products/program/{p.name}"
        mapping[f"reports/five-products/{p.name}"] = new_rel
        moved.append((p, dst, new_rel))

    # Rewrite insides of moved files (depth + repo path string)
    for _old, dst, _new_rel in moved:
        text = dst.read_text(encoding="utf-8")
        text2 = _rewrite_moved_relative(text)
        text2 = _rewrite_repo_refs(text2, mapping)
        if text2 != text:
            dst.write_text(text2, encoding="utf-8")
            subprocess.check_call(["git", "add", str(dst)], cwd=ROOT)

    # Stubs at old paths
    for old, _dst, new_rel in moved:
        # git mv removed old; recreate stub at old path
        stub_path = SRC / old.name
        # Relative link from reports/five-products/ to new location
        if new_rel.startswith("docs/"):
            rel_link = f"../../{new_rel}"
        else:
            # reports/products/five-products/program/X from reports/five-products/
            rel_link = f"../products/five-products/program/{old.name}"
        _stub(stub_path, rel_link)

    # Root README
    readme = SRC / "README.md"
    if not readme.exists() or "已迁移" not in readme.read_text(encoding="utf-8"):
        readme.write_text(
            "\n".join(
                [
                    "---",
                    "doc_type: Index",
                    "status: active",
                    "authority: supporting",
                    "doc_id: STUB_FIVE_PRODUCTS_ROOT",
                    "last_reviewed: 2026-11-15",
                    "---",
                    "",
                    "# reports/five-products（根目录已收口）",
                    "",
                    "> ADR / 决策正文 → [`../../docs/decisions/products/five-products/`](../../docs/decisions/products/five-products/)",
                    "> 程序/状态/验收叙事 → [`../products/five-products/program/`](../products/five-products/program/)",
                    "> ops → [`../products/five-products/ops/`](../products/five-products/ops/)",
                    "> contracts → [`../../docs/contracts/products/five-products/`](../../docs/contracts/products/five-products/)",
                    "",
                    "根下各 `*.md` 现为 Index stub；脚本请改指向新路径或继续经 stub 跳转。",
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.check_call(["git", "add", str(readme)], cwd=ROOT)

    # Rewrite remaining repo references (scripts, packages, docs) excluding stubs we just wrote
    skip_parts = {
        "reports/five-products",  # stubs + README — keep old path strings? No: stubs should mention new path only
    }
    exts = {".md", ".py", ".sh", ".yml", ".yaml", ".json", ".ts", ".tsx", ".txt"}
    changed = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        if ".git" in path.parts or "node_modules" in path.parts or ".venv" in path.parts:
            continue
        # Don't rewrite the stub files' "正文已迁至" targets incorrectly — stubs use relative links
        if path.parent == SRC and path.suffix == ".md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        text2 = _rewrite_repo_refs(text, mapping)
        if text2 != text:
            path.write_text(text2, encoding="utf-8")
            subprocess.check_call(["git", "add", str(path)], cwd=ROOT)
            changed += 1

    print(
        f"OK migrated decisions+drafts={len(decisions)} program={len(program)} "
        f"repo_files_rewritten={changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
