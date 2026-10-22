#!/usr/bin/env python3
"""
CAPABILITIES.md 统计表一致性 / 生成物新鲜度（Phase C）

源码为真：章节表格中的 ✅/⚠️ 行是产品能力声明计数来源。
统计表块（`<!-- AUTO-STATS:BEGIN -->` … `<!-- AUTO-STATS:END -->`）是**纯生成物**，
必须与章节实算全文一致（与影响矩阵同款临时全文 diff 语义）。

用法:
  python3 scripts/verify_capability_consistency.py           # 新鲜度检查，exit 0/1
  python3 scripts/verify_capability_consistency.py --fix    # 重写 AUTO-STATS 块 + frontmatter
  python3 scripts/generate_capability_stats.py               # 同上 --fix 的薄入口

退出码: 0=一致, 1=不一致/过期
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES = ROOT / "AIPLAT_CAPABILITIES.md"

STATS_BEGIN = "<!-- AUTO-STATS:BEGIN -->"
STATS_END = "<!-- AUTO-STATS:END -->"
# Legacy single-line marker (migrated on --fix / first render)
STATS_LEGACY = "<!-- AUTO-STATS -->"

# ── 章节 → 统计表维度映射（顺序 = 生成表行序）──
CHAPTER_MAP: dict[str, str] = {
    "一、Harness 执行引擎": "Harness 执行引擎",
    "二、记忆子系统": "记忆子系统",
    "三、知识引擎（本体）": "知识引擎（本体）",
    "四、RAG 检索": "RAG 检索",
    "四附、知识基础设施": "知识基础设施",
    "五、Agent 系统": "Agent 系统",
    "六、Skill 系统": "Skill 系统",
    "七、安全与治理": "安全与治理",
    "八、可观测性": "可观测性",
    "九、模型基础设施": "模型基础设施",
    "十、部署与运维": "部署与运维",
    "十一、扩展与学习": "扩展与学习",
    "十二、Gate 系统": "Gate 系统",
    "十三、评估系统": "评估系统",
    "十四、MCP 协议": "MCP 协议",
    "十四附、A2A 协议": "A2A 协议",
    "十五、文档智能": "文档智能",
    "十六、工具生态": "工具生态",
    "十七、微调系统": "微调系统",
    "十八、部署与灰度": "部署与灰度",
    "十九、运行时干预": "运行时干预",
    "二十、Arena & 调度": "Arena & 调度",
    "二十一、平台治理": "平台治理",
    "二十二、Infra 基础设施": "Infra 基础设施",
    "二十三、核心API统一入口": "核心API统一入口",
    "二十四、编排系统": "编排系统",
    "二十五、管理 & 质量": "管理 & 质量",
    "二十六、编排层 (Orchestration)": "编排层",
    "二十七、L6 自主能力": "L6 自主能力",
    "二十八、记忆系统白盒化": "记忆系统白盒化",
    "二十九、记忆运行时过滤": "记忆运行时过滤",
    "三十、MoA 多模型推理": "MoA多模型推理",
    "三十一、AI知识层增强": "AI知识层增强",
    "三十二、Hermes压缩对标": "Hermes压缩对标",
    "三十三、Scenario Simulation": "Scenario Simulation",
    "三十四、Decision Lineage": "Decision Lineage",
    "三十五、Security 3D": "Security 3D 增强",
    "三十六、Global Branching": "Global Branching",
    "三十七、EvoX 蜂群协作": "EvoX 蜂群协作",
    "三十八、闭环执行层": "闭环执行层",
    "三十九、知识编译与OKF": "知识编译与OKF",
    "四十、对话→Wiki 自动管线": "对话→Wiki 自动管线",
    "四十一、Skill 目录标准化": "Skill 目录标准化",
    "四十一、Web 工具归并": "Web 工具归并",
    "四十一、E2E端到端验证": "E2E 端到端验证",
}


def count_checks_in_section(content: str, section_title: str) -> Tuple[int, int]:
    """Count ✅ (implemented) and ⚠️ (partial) in a section table (3rd column)."""
    pattern = rf"^## {re.escape(section_title)}"
    lines = content.split("\n")
    start = -1
    for i, line in enumerate(lines):
        if re.match(pattern, line):
            start = i + 1
            break
    if start == -1:
        return 0, 0

    implemented = 0
    partial = 0
    for line in lines[start:]:
        if line.startswith("## ") and not line.startswith("###"):
            break
        if line.startswith("|---") or line.startswith("| ---") or line.startswith("|:--"):
            continue
        if not line.startswith("| "):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        status = parts[3]
        if status.startswith("✅"):
            implemented += 1
        elif status.startswith("⚠"):
            partial += 1
    return implemented, partial


def compute_section_counts(content: str) -> Dict[str, Tuple[int, int]]:
    """Return {stat_dim: (implemented, partial)} from chapter bodies."""
    out: Dict[str, Tuple[int, int]] = {}
    for section_title, stat_dim in CHAPTER_MAP.items():
        out[stat_dim] = count_checks_in_section(content, section_title)
    return out


def render_stats_block(content: str) -> str:
    """Render AUTO-STATS inner markdown (no BEGIN/END markers) from chapter counts."""
    counts = compute_section_counts(content)
    lines: List[str] = [
        "| 维度 | 已实现 | 部分实现 | 合计 |",
        "|------|:---:|:---:|:---:|",
    ]
    total_impl = 0
    total_part = 0
    # Preserve CHAPTER_MAP insertion order; skip duplicate dim names
    seen = set()
    for _section, dim in CHAPTER_MAP.items():
        if dim in seen:
            continue
        seen.add(dim)
        impl, part = counts.get(dim, (0, 0))
        total_impl += impl
        total_part += part
        lines.append(f"| {dim} | {impl} | {part} | {impl + part} |")
    lines.append(
        f"| **总计** | **{total_impl}** | **{total_part}** | **{total_impl + total_part}** |"
    )
    return "\n".join(lines) + "\n"


def extract_stats_block(content: str) -> Optional[str]:
    """Return current AUTO-STATS inner body, or None if markers missing."""
    if STATS_BEGIN in content and STATS_END in content:
        m = re.search(
            re.escape(STATS_BEGIN) + r"\n(.*)" + re.escape(STATS_END),
            content,
            re.DOTALL,
        )
        return m.group(1) if m else None
    # Legacy: from <!-- AUTO-STATS --> through the **总计** row
    if STATS_LEGACY in content:
        m = re.search(
            re.escape(STATS_LEGACY) + r"\n(.*?\|\s*\*\*总计\*\*.*?\n)",
            content,
            re.DOTALL,
        )
        return m.group(1) if m else None
    return None


def apply_stats(content: str) -> Tuple[str, int, int]:
    """Replace AUTO-STATS block + sync frontmatter total_capabilities.

    Returns (new_content, total_impl, total_part).
    """
    block = render_stats_block(content)
    counts = compute_section_counts(content)
    total_impl = sum(c[0] for c in counts.values())
    total_part = sum(c[1] for c in counts.values())
    fm_total = total_impl + total_part

    wrapped = f"{STATS_BEGIN}\n{block}{STATS_END}"

    if STATS_BEGIN in content and STATS_END in content:
        new = re.sub(
            re.escape(STATS_BEGIN) + r"\n.*?" + re.escape(STATS_END),
            wrapped,
            content,
            count=1,
            flags=re.DOTALL,
        )
    elif STATS_LEGACY in content:
        # Replace legacy marker + table through **总计** row
        new = re.sub(
            re.escape(STATS_LEGACY) + r"\n.*?\|\s*\*\*总计\*\*.*?\n",
            wrapped + "\n",
            content,
            count=1,
            flags=re.DOTALL,
        )
    else:
        # Insert after ## 统计
        if "## 统计" not in content:
            raise ValueError("AIPLAT_CAPABILITIES.md missing ## 统计 section")
        new = content.replace(
            "## 统计\n",
            f"## 统计\n\n{wrapped}\n",
            1,
        )

    new = re.sub(
        r"^total_capabilities:\s*\d+",
        f"total_capabilities: {fm_total}",
        new,
        count=1,
        flags=re.MULTILINE,
    )
    return new, total_impl, total_part


def check_stats_fresh(path: Optional[Path] = None) -> int:
    """Worktree AUTO-STATS block must ≡ chapter render. Return 0/1. Does not rewrite."""
    path = path or CAPABILITIES
    content = path.read_text(encoding="utf-8")
    expected = render_stats_block(content)
    actual = extract_stats_block(content)
    if actual is None:
        print("ERROR: missing AUTO-STATS markers in AIPLAT_CAPABILITIES.md")
        print(f"  expected markers: {STATS_BEGIN} … {STATS_END}")
        print("  Fix: python3 scripts/generate_capability_stats.py")
        return 1
    # Normalize trailing newlines for compare
    if actual.rstrip("\n") + "\n" == expected:
        # Also require frontmatter sync
        counts = compute_section_counts(content)
        fm_total = sum(c[0] + c[1] for c in counts.values())
        fm = re.search(r"^total_capabilities:\s*(\d+)", content, re.MULTILINE)
        if fm and int(fm.group(1)) != fm_total:
            print(
                f"ERROR: frontmatter total_capabilities={fm.group(1)} "
                f"!= stats render total={fm_total}"
            )
            print("  Fix: python3 scripts/generate_capability_stats.py")
            return 1
        print(f"OK: CAPABILITIES AUTO-STATS matches chapter render ({path.name})")
        return 0

    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(expected)
        tmp = tf.name
    print("ERROR: AIPLAT_CAPABILITIES.md AUTO-STATS stale vs chapter ✅/⚠️ counts")
    print(f"  regenerated: {tmp}")
    print(f"  worktree:    {path}")
    print("  Fix: python3 scripts/generate_capability_stats.py")
    a_lines = actual.rstrip("\n").splitlines()
    e_lines = expected.rstrip("\n").splitlines()
    diffs = 0
    for i, (a, e) in enumerate(zip(a_lines, e_lines)):
        if a != e:
            print(f"  line {i + 1}:")
            print(f"    - {a}")
            print(f"    + {e}")
            diffs += 1
            if diffs >= 8:
                break
    if len(a_lines) != len(e_lines):
        print(f"  length: worktree={len(a_lines)} expected={len(e_lines)}")
    return 1


def fix(path: Optional[Path] = None) -> None:
    """Rewrite AUTO-STATS block + frontmatter from chapter counts."""
    path = path or CAPABILITIES
    content = path.read_text(encoding="utf-8")
    new, total_impl, total_part = apply_stats(content)
    path.write_text(new, encoding="utf-8")
    print(
        f"  ✅ AUTO-STATS + frontmatter recalculated: "
        f"{total_impl}✅ + {total_part}⚠️ = {total_impl + total_part}"
    )


def parse_stats_table(content: str) -> Dict[str, Tuple[int, int, int]]:
    """Parse the stats table, return {dimension: (implemented, partial, total)}."""
    block = extract_stats_block(content) or ""
    stats: Dict[str, Tuple[int, int, int]] = {}
    for line in block.split("\n"):
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 4:
            continue
        dim = parts[0].replace("*", "")
        if dim in ("维度", "总计"):
            continue
        try:
            impl = int(parts[1].replace("*", ""))
            part = int(parts[2].replace("*", ""))
            tot = int(parts[3].replace("*", ""))
            stats[dim] = (impl, part, tot)
        except (ValueError, IndexError):
            continue
    return stats


def main() -> int:
    """Freshness gate: AUTO-STATS ≡ chapter render (+ frontmatter)."""
    return check_stats_fresh(CAPABILITIES)


if __name__ == "__main__":
    if "--fix" in sys.argv:
        fix()
        sys.exit(0)
    sys.exit(main())
