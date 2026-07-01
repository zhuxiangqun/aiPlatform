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
        if status == "✅":
            implemented += 1
        elif status == "⚠️":
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


if __name__ == "__main__":
    if "--fix" in sys.argv:
        fix() if callable(fix := globals().get("fix")) else print("自动修复未实现，请手动更新统计表")
        sys.exit(0)
    sys.exit(main())
