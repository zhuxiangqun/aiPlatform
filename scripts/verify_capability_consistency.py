#!/usr/bin/env python3
"""
CAPABILITIES.md 一致性验证脚本

验证:
  1. 统计表的 "已实现" 总数 = 各章节 ✅ 计数之和
  2. 统计表的 "合计" = 已实现 + 部分实现
  3. 章节 ✅ 计数与统计表行一致

用法:
  python3 scripts/verify_capability_consistency.py [--fix]
  --fix: 自动更新统计表（需 AIPLAT_CAPABILITIES.md 中存在标记 <!-- AUTO-STATS -->

退出码: 0=一致, 1=不一致
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES = ROOT / "AIPLAT_CAPABILITIES.md"

# ── 章节 → 统计表维度映射 ──
CHAPTER_MAP: dict[str, str] = {
    "一、Harness 执行引擎":    "Harness 执行引擎",
    "二、记忆子系统":          "记忆子系统",
    "三、知识引擎（本体）":     "知识引擎（本体）",
    "四、RAG 检索":           "RAG 检索",
    "四附、知识基础设施":       "知识基础设施",
    "五、Agent 系统":         "Agent 系统",
    "六、Skill 系统":         "Skill 系统",
    "七、安全与治理":          "安全与治理",
    "八、可观测性":            "可观测性",
    "九、模型基础设施":         "模型基础设施",
    "十、部署与运维":          "部署与运维",
    "十一、扩展与学习":         "扩展与学习",
    "十二、Gate 系统":         "Gate 系统",
    "十三、评估系统":           "评估系统",
    "十四、MCP 协议":         "MCP 协议",
    "十四附、A2A 协议":        "A2A 协议",
    "十五、文档智能":           "文档智能",
    "十六、工具生态":           "工具生态",
    "十七、微调系统":           "微调系统",
    "十八、部署与灰度":         "部署与灰度",
    "十九、运行时干预":         "运行时干预",
    "二十、Arena & 调度":      "Arena & 调度",
    "二十一、平台治理":         "平台治理",
    "二十二、Infra 基础设施":   "Infra 基础设施",
    "二十三、核心API统一入口":  "核心API统一入口",
    "二十四、编排系统":         "编排系统",
    "二十五、管理 & 质量":      "管理 & 质量",
    "二十六、编排层 (Orchestration)": "编排层",
    "二十七、L6 自主能力":     "L6 自主能力",
    "二十八、记忆系统白盒化":   "记忆系统白盒化",
    "二十九、记忆运行时过滤":   "记忆运行时过滤",
    "三十、MoA 多模型推理":    "MoA多模型推理",
    "三十一、AI知识层增强":     "AI知识层增强",
    "三十二、Hermes压缩对标":   "Hermes压缩对标",
    "三十三、Scenario Simulation": "Scenario Simulation",
    "三十四、Decision Lineage": "Decision Lineage",
    "三十五、Security 3D":     "Security 3D 增强",
    "三十六、Global Branching": "Global Branching",
    "三十七、EvoX 蜂群协作":    "EvoX 蜂群协作",
    "三十八、闭环执行层":       "闭环执行层",
    "三十九、知识编译与OKF":    "知识编译与OKF",
    "四十、对话→Wiki 自动管线": "对话→Wiki 自动管线",
    "四十一、Web 工具归并":     "Web 工具归并",
    "四十一、Skill 目录标准化": "Skill 目录标准化",
    "四十一、E2E端到端验证":   "E2E 端到端验证",
}


def count_checks_in_section(content: str, section_title: str) -> tuple[int, int]:
    """Count ✅ (implemented) and ⚠️ (partial) in a section.
    
    CAPABILITIES format: | name | location | ✅/⚠️ | description | status |
    We count the 3rd column value.
    """
    pattern = rf'^## {re.escape(section_title)}'
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
    in_separator = False
    for line in lines[start:]:
        if line.startswith("## ") and not line.startswith("###"):
            break
        # Skip header rows and separators
        if line.startswith("|---") or line.startswith("| ---") or line.startswith("|:--"):
            in_separator = True
            continue
        if not line.startswith("| "):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        # parts[0] is empty (leading |), parts[1] name, parts[2] location, parts[3] status
        status = parts[3]
        if status.startswith("✅"):
            implemented += 1
        elif status.startswith("⚠"):
            partial += 1

    return implemented, partial


def parse_stats_table(content: str) -> dict[str, tuple[int, int, int]]:
    """Parse the stats table, return {dimension: (implemented, partial, total)}."""
    in_table = False
    stats: dict[str, tuple[int, int, int]] = {}
    for line in content.split("\n"):
        if "## 统计" in line:
            in_table = True
            continue
        if in_table and line.startswith("---"):
            break
        if not in_table or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 4:
            continue
        dim = parts[0]
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
    content = CAPABILITIES.read_text(encoding="utf-8")
    errors = 0

    # 1. Count per section vs stats table
    stats = parse_stats_table(content)
    section_counts: dict[str, tuple[int, int]] = {}

    for section_title, stat_dim in CHAPTER_MAP.items():
        impl, part = count_checks_in_section(content, section_title)
        section_counts[stat_dim] = (impl, part)

        if stat_dim in stats:
            s_impl, s_part, s_total = stats[stat_dim]
            # Compare: implemented count
            if impl != s_impl:
                print(f"  ❌ {stat_dim}: 章节 ✅={impl}, 统计表已实现={s_impl}")
                errors += 1
            # Compare: total
            expected_total = impl + part
            if s_total != expected_total:
                print(f"  ⚠️ {stat_dim}: 合计={s_total}, 预期={expected_total} (✅{impl}+⚠️{part})")

    # 2. Total sum check
    is_total_row = lambda d: "总计" in d
    total_impl_from_sections = sum(t[0] for t in section_counts.values())
    total_part_from_sections = sum(t[1] for t in section_counts.values())
    stat_impl_sum = sum(s[0] for dim, s in stats.items() if not is_total_row(dim))
    stat_part_sum = sum(s[1] for dim, s in stats.items() if not is_total_row(dim))

    if total_impl_from_sections != stat_impl_sum:
        print(f"\n  ❌ 已实现总计不匹配: 章节 ✅ 求和={total_impl_from_sections}, 统计表求和={stat_impl_sum}")
        errors += 1
    else:
        print(f"  ✅ 已实现总计一致: {total_impl_from_sections}")

    # 3. Check for dimensions in stats but not in chapter map (orphan rows)
    known = set(CHAPTER_MAP.values())
    stat_dims = {k for k in stats if not is_total_row(k)}
    missing = stat_dims - known
    extra = known - stat_dims
    if missing:
        print(f"  ⚠️ 统计表中未在章节映射中的维度: {missing}")
    if extra:
        print(f"  ⚠️ 章节映射中有但统计表无: {extra}")

    if errors == 0:
        print("\n  ✅ AIPLAT_CAPABILITIES.md 一致性验证通过")
        return 0
    else:
        print(f"\n  ❌ {errors} 处不一致")
        return 1


def fix() -> None:
    """Auto-fix: recalculate stats table from actual section counts and write back."""
    content = CAPABILITIES.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Step 1: Count actual per-section entries
    actual: dict[str, tuple[int, int]] = {}
    for section_title in CHAPTER_MAP:
        impl, part = count_checks_in_section(content, section_title)
        actual[section_title] = (impl, part)

    # Step 2: Rebuild the file with corrected stats table
    new_lines: list[str] = []
    in_stats = False
    in_table_rows = False
    total_impl = 0
    total_part = 0
    STATS_HEADER = lines.index([l for l in lines if "## 统计" in l][0]) if any("## 统计" in l for l in lines) else -1

    for i, line in enumerate(lines):
        if "## 统计" in line:
            in_stats = True
            new_lines.append(line)
            continue
        if in_stats and not in_table_rows and line.startswith("|") and ("------" in line or ":--" in line):
            in_table_rows = True
            new_lines.append(line)
            continue
        if in_stats and in_table_rows and line.startswith("|"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if not parts:
                new_lines.append(line)
                continue
            dim = parts[0].replace("*", "")
            if dim == "总计":
                for (i_val, p_val) in actual.values():
                    total_impl += i_val
                    total_part += p_val
                new_lines.append(f"| **总计** | **{total_impl}** | **{total_part}** | **{total_impl + total_part}** |")
                continue
            # Find matching section
            section_title = None
            for st in CHAPTER_MAP:
                if st == dim:
                    section_title = st
                    break
            if section_title and section_title in actual:
                i_val, p_val = actual[section_title]
                new_lines.append(f"| {dim} | {i_val} | {p_val} | {i_val + p_val} |")
                continue
            # Not a recognized dimension row — pass through
            new_lines.append(line)
            continue
        if in_stats and in_table_rows and not line.startswith("|"):
            in_stats = False
            in_table_rows = False
        new_lines.append(line)

    if total_impl > 0:
        CAPABILITIES.write_text("\n".join(new_lines), encoding="utf-8")
        print(f"  ✅ Stats table recalculated: {total_impl}✅ + {total_part}⚠️ = {total_impl + total_part}")
    else:
        print("  ⚠ No changes (stats table not found)")


if __name__ == "__main__":
    if "--fix" in sys.argv:
        fix()
        sys.exit(0)
    sys.exit(main())
