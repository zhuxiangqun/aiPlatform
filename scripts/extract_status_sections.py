#!/usr/bin/env python3
"""
extract_status_sections.py — 确定性 CLAUDE.md 瘦身外迁器（阶段一 P1b）

依据 classify_claude_sections.py 的分类：
  - STATUS 节  → 整节迁到 docs/PHASE_STATUS.md，CLAUDE.md 原处留指针（保留编号锚点）
  - MIXED 节   → 段落级拆分：把「纯状态段落」(含日期/Phase/已修复/已知违规 且 0 条规则标记) 迁出，
                 规则段落全部留下；带**每节规则标记守恒校验**，任一节校验失败则该节整节保留（零风险回退）
  - RULE/OTHER → 原样保留

安全底线（对应 CLAUDE.md §5.84 draft+confirm）：
  - 不直接改 CLAUDE.md。输出 draft: aiPlat-core/CLAUDE.md.slim.draft
  - 全局规则标记守恒硬校验：draft 中 (强制|禁止|必须|MUST|红线) 行数必须 == 原文，否则退出码 1
  - 输出 diff 供人工审阅

用法:
  python3 scripts/extract_status_sections.py           # 生成 PHASE_STATUS.md + CLAUDE.md.slim.draft + 打印统计
  python3 scripts/extract_status_sections.py --diff     # 额外打印 unified diff

退出码: 0=安全(守恒通过), 1=守恒失败(不写 draft)
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_claude_sections import parse_sections, classify  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[1]
CLAUDE_MD = WORKSPACE / "aiPlat-core" / "CLAUDE.md"
DRAFT = WORKSPACE / "aiPlat-core" / "CLAUDE.md.slim.draft"
PHASE_STATUS = WORKSPACE / "docs" / "PHASE_STATUS.md"

RULE_MARKER = re.compile(r"强制|禁止|必须|\bMUST\b|红线")
# 纯状态段落的起始信号（段落级）
STATUS_BLOCK = re.compile(
    r"当前已知违规|当前实现状态|当前状态|已修复|已知例外|截至 ?20\d{2}"
    r"|Phase ?\d+ ?(进度|完成|状态)|当前 .*质量状态|实施状态|已删除|已激活"
)
DATE_OR_PHASE = re.compile(r"20\d{2}-\d{2}|Phase ?\d+")


def _rule_markers(text: str) -> int:
    return len(RULE_MARKER.findall(text))


def _pointer_stub(number: str) -> str:
    return (
        f"> 📦 状态明细已迁至 `docs/PHASE_STATUS.md`（§{number}）。"
        f"编号保留以维持交叉引用。\n"
    )


def _split_paragraphs(body_lines):
    """Split into blocks separated by blank lines. Returns list of (start_idx, lines)."""
    blocks = []
    cur = []
    cur_start = 0
    for i, ln in enumerate(body_lines):
        if ln.strip() == "":
            if cur:
                blocks.append((cur_start, cur))
                cur = []
            # keep blank as its own separator block
            blocks.append((i, [ln]))
        else:
            if not cur:
                cur_start = i
            cur.append(ln)
    if cur:
        blocks.append((cur_start, cur))
    return blocks


def transform_status(sec, lines):
    """STATUS: heading kept, body → pointer stub. Full section → PHASE_STATUS."""
    heading = lines[sec.start - 1]
    claude_out = [heading, "\n", _pointer_stub(sec.number), "\n"]
    status_out = list(lines[sec.start - 1:sec.end])
    if status_out and status_out[-1].strip() != "":
        status_out.append("\n")
    return claude_out, status_out, sec.line_count - len(claude_out)


def transform_mixed(sec, lines):
    """MIXED: move pure-status paragraphs, keep rule paragraphs.
    Per-section conservation gate: if retained rule-marker count != original,
    revert to whole-section-kept (move nothing)."""
    heading = lines[sec.start - 1]
    body = lines[sec.start:sec.end]  # excludes heading line
    orig_rules = _rule_markers("".join(lines[sec.start - 1:sec.end]))

    kept = [heading]
    moved = []
    blocks = _split_paragraphs(body)
    moved_any = False
    for _, blk in blocks:
        btext = "".join(blk)
        is_status_block = (
            STATUS_BLOCK.search(btext)
            and DATE_OR_PHASE.search(btext)
            and _rule_markers(btext) == 0
        )
        if is_status_block:
            moved.extend(blk)
            moved_any = True
        else:
            kept.extend(blk)

    kept_rules = _rule_markers("".join(kept))
    # Conservation gate: retained rules must equal original. Else keep whole.
    if kept_rules != orig_rules or not moved_any:
        whole = list(lines[sec.start - 1:sec.end])
        return whole, [], 0

    # Insert a pointer note after heading
    claude_out = [heading, "\n", _pointer_stub(sec.number), "\n"] + kept[1:]
    status_out = [heading] + moved
    if status_out and status_out[-1].strip() != "":
        status_out.append("\n")
    saved = sec.line_count - len(claude_out)
    return claude_out, status_out, saved


def main() -> int:
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines(keepends=True)
    sections = parse_sections(lines)
    for s in sections:
        classify(s)

    preamble = lines[: sections[0].start - 1]
    postamble = lines[sections[-1].end:]

    claude_draft = list(preamble)
    status_doc = [
        "# aiPlat Phase 状态时间线（从 CLAUDE.md 外迁）\n", "\n",
        "> 本文件汇集各 Phase 的实现状态快照，从 `aiPlat-core/CLAUDE.md` 迁出，"
        "使 CLAUDE.md 聚焦耐久治理规则。\n",
        "> 能力清单见 `AIPLAT_CAPABILITIES.md`；治理规则见 `aiPlat-core/CLAUDE.md`。\n", "\n",
        "last_synced: 2026-07-06\n", "\n", "---\n", "\n",
    ]

    total_saved = 0
    moved_sections = 0
    deferred_mixed = []
    for s in sections:
        if s.tag == "STATUS":
            c_out, s_out, saved = transform_status(s, lines)
            claude_draft.extend(c_out)
            status_doc.extend(s_out)
            total_saved += saved
            moved_sections += 1
        elif s.tag == "MIXED":
            # MIXED status is interleaved with rule markers; auto-splitting is
            # unsafe (orphan headings / misleading pointers). Keep 100% intact
            # in the automated pass — defer to human-guided hand-split.
            claude_draft.extend(lines[s.start - 1:s.end])
            deferred_mixed.append((s.number, s.title, s.line_count))
        else:  # RULE / OTHER
            claude_draft.extend(lines[s.start - 1:s.end])
    claude_draft.extend(postamble)

    # ── Conservation gate (global, hard) ──
    orig_text = "".join(lines)
    draft_text = "".join(claude_draft)
    orig_rules = _rule_markers(orig_text)
    draft_rules = _rule_markers(draft_text)
    moved_rules = _rule_markers("".join(status_doc))

    print(f"原始行数:   {len(lines)}")
    print(f"draft 行数: {len(claude_draft)}  (削减 {len(lines) - len(claude_draft)})")
    print(f"外迁节数:   {moved_sections}")
    print(f"规则标记 (强制|禁止|必须|MUST|红线): 原 {orig_rules} → 留 {draft_rules} + 迁 {moved_rules}")

    if draft_rules != orig_rules:
        print(f"❌ 规则标记守恒失败: 原 {orig_rules} ≠ draft {draft_rules}。不写 draft。", file=sys.stderr)
        return 1
    print("✓ 规则标记守恒通过 (draft 保留全部规则句)")

    # ── §编号锚点守恒: 所有原 §编号仍在 draft 中出现 ──
    orig_nums = set(re.findall(r"^#{2,3} (5\.\d+) ", orig_text, re.MULTILINE))
    draft_nums = set(re.findall(r"^#{2,3} (5\.\d+) ", draft_text, re.MULTILINE))
    lost = orig_nums - draft_nums
    if lost:
        print(f"❌ 丢失 §编号锚点: {sorted(lost)}。不写 draft。", file=sys.stderr)
        return 1
    print(f"✓ §编号锚点守恒通过 ({len(draft_nums)} 个编号全部保留)")

    DRAFT.write_text(draft_text, encoding="utf-8")
    PHASE_STATUS.parent.mkdir(parents=True, exist_ok=True)
    PHASE_STATUS.write_text("".join(status_doc), encoding="utf-8")
    print(f"\ndraft → {DRAFT.relative_to(WORKSPACE)}")
    print(f"迁出目标 → {PHASE_STATUS.relative_to(WORKSPACE)} ({len(status_doc)} 行)")

    if deferred_mixed:
        print(f"\n⏸  MIXED 节保持原样 (需人工拆分, {len(deferred_mixed)} 节, "
              f"{sum(n for _, _, n in deferred_mixed)} 行):")
        for num, title, n in deferred_mixed:
            print(f"    §{num:6} {n:3}行  {title[:40]}")

    if "--diff" in sys.argv:
        diff = difflib.unified_diff(
            lines, claude_draft,
            fromfile="aiPlat-core/CLAUDE.md", tofile="aiPlat-core/CLAUDE.md.slim.draft",
            n=1,
        )
        print("".join(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
