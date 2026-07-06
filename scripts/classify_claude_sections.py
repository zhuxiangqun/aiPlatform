#!/usr/bin/env python3
"""
classify_claude_sections.py — 确定性 CLAUDE.md §5.NNN 小节分类器

目的（文档治理阶段一 P1a）：
  把 aiPlat-core/CLAUDE.md 的每个 `### 5.NNN` 小节分类为：
    - RULE   : 耐久治理规则（强制/红线/禁止/边界）→ 留在 CLAUDE.md
    - STATUS : 阶段状态快照（日期/计数/端点/模块/Phase X.Y 注册）→ 迁到 docs/PHASE_STATUS.md
    - MIXED  : 既含规则又含状态 → 拆分（规则留，状态迁）
    - OTHER  : 信号不足 → 人工裁定

这是纯确定性文本分析，不调用任何 LLM / 评估器。输出供人工审阅确认（§5.84 draft+confirm）。

用法:
  python3 scripts/classify_claude_sections.py            # 打印 + 写 reports/claude_section_classification.md
  python3 scripts/classify_claude_sections.py --json     # 额外输出 JSON 到 stdout

退出码: 0 恒定（分类是建议，不阻断）
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

WORKSPACE = Path(__file__).resolve().parents[1]
CLAUDE_MD = WORKSPACE / "aiPlat-core" / "CLAUDE.md"
REPORT = WORKSPACE / "reports" / "claude_section_classification.md"

# §5.NN headings appear at both h2 (`## 5.29`) and h3 (`### 5.35`) levels.
SECTION_RE = re.compile(r"^#{2,3} (5\.\d+)\s+(.*)$")

# STATUS 信号：点时快照 / 计数 / Phase 注册
STATUS_PATTERNS = [
    r"20\d{2}-\d{2}",              # 日期 2026-07
    r"\d+\s*个?\s*模块",           # N 模块 / N 个模块
    r"\d+\s*端点",                 # N 端点
    r"\d+\s*步",                   # N 步（管线）
    r"Phase\s*\d+(\.\d+)?",        # Phase 10.1 注册
    r"总览",
    r"数据模型",
    r"最终形态",
    r"API\s*端点更新",
    r"对齐能力",
    r"四重强化",
    r"多域知识库架构",
]

# RULE 信号：耐久规则
RULE_PATTERNS = [
    r"强制",
    r"红线",
    r"禁止",
    r"必须",
    r"\bMUST\b",
    r"边界",
    r"原则",
    r"规范",
    r"（强制",
    r"安全红线",
]


@dataclass
class Section:
    number: str
    title: str
    start: int          # 1-indexed line of the ### heading
    end: int            # 1-indexed line before next heading (inclusive)
    body: str = ""
    tag: str = "OTHER"
    reasons: List[str] = field(default_factory=list)

    @property
    def line_count(self) -> int:
        return self.end - self.start + 1


def _match_any(patterns: List[str], text: str) -> List[str]:
    hits = []
    for p in patterns:
        if re.search(p, text):
            hits.append(p)
    return hits


def parse_sections(lines: List[str]) -> List[Section]:
    sections: List[Section] = []
    for i, line in enumerate(lines):
        m = SECTION_RE.match(line.rstrip("\n"))
        if m:
            sections.append(Section(number=m.group(1), title=m.group(2).strip(), start=i + 1, end=i + 1))
    # compute end boundaries: next section start - 1, last goes to EOF or next `## ` header
    for idx, sec in enumerate(sections):
        if idx + 1 < len(sections):
            sec.end = sections[idx + 1].start - 1
        else:
            # extend to next top-level (## ) header or EOF
            end = len(lines)
            for j in range(sec.start, len(lines)):
                if re.match(r"^## (?!#)", lines[j]) and j + 1 > sec.start:
                    end = j
                    break
            sec.end = end
        sec.body = "".join(lines[sec.start - 1:sec.end])
    return sections


def classify(sec: Section) -> None:
    # Already-migrated pointer stub → POINTER (idempotent: extractor won't re-migrate,
    # guard won't re-flag). Detected by the migration marker in the body.
    if "状态明细已迁至" in sec.body:
        sec.tag = "POINTER"
        sec.reasons.append("migrated-stub")
        return
    text = sec.title + "\n" + sec.body
    status_hits = _match_any(STATUS_PATTERNS, text)
    rule_hits = _match_any(RULE_PATTERNS, text)
    # Rule signal weighted by count of mandatory markers in body (stronger evidence)
    mandatory_marker_count = len(re.findall(r"强制|禁止|必须|\bMUST\b|红线", sec.body))

    has_status = bool(status_hits)
    has_rule = bool(rule_hits)

    if has_rule and has_status:
        sec.tag = "MIXED"
    elif has_rule:
        sec.tag = "RULE"
    elif has_status:
        sec.tag = "STATUS"
    else:
        sec.tag = "OTHER"

    if status_hits:
        sec.reasons.append(f"status:{','.join(sorted(set(status_hits)))[:60]}")
    if rule_hits:
        sec.reasons.append(f"rule×{mandatory_marker_count}")


def build_report(sections: List[Section]) -> str:
    by_tag = {"RULE": [], "STATUS": [], "MIXED": [], "OTHER": [], "POINTER": []}
    for s in sections:
        by_tag[s.tag].append(s)

    total = sum(s.line_count for s in sections)
    status_lines = sum(s.line_count for s in by_tag["STATUS"])
    mixed_lines = sum(s.line_count for s in by_tag["MIXED"])
    rule_lines = sum(s.line_count for s in by_tag["RULE"])
    other_lines = sum(s.line_count for s in by_tag["OTHER"])

    out = []
    out.append("# CLAUDE.md §5.NNN 分类报告（阶段一 P1a — 待人工确认）")
    out.append("")
    out.append("> 确定性分类，供逐节 confirm/override（§5.84 draft+confirm）。")
    out.append("> STATUS → 迁 `docs/PHASE_STATUS.md`；MIXED → 拆分（规则留/状态迁）；RULE/OTHER → 留。")
    out.append("")
    out.append("## 汇总")
    out.append("")
    out.append("| 分类 | 小节数 | 行数 | 处理 |")
    out.append("|------|:---:|:---:|------|")
    out.append(f"| RULE (留) | {len(by_tag['RULE'])} | {rule_lines} | 保留，至多轻压缩 |")
    out.append(f"| STATUS (迁) | {len(by_tag['STATUS'])} | {status_lines} | 整节迁 PHASE_STATUS.md |")
    out.append(f"| MIXED (拆) | {len(by_tag['MIXED'])} | {mixed_lines} | 规则留，状态迁 |")
    out.append(f"| OTHER (裁) | {len(by_tag['OTHER'])} | {other_lines} | 人工裁定 |")
    out.append(f"| **合计** | **{len(sections)}** | **{total}** | — |")
    out.append("")
    est_removable = status_lines + int(mixed_lines * 0.5)
    out.append(f"**可迁出估算**：STATUS 全量 {status_lines} 行 + MIXED 约半 {int(mixed_lines*0.5)} 行 ≈ **{est_removable} 行**")
    out.append("")

    for tag in ("STATUS", "MIXED", "OTHER", "RULE", "POINTER"):
        secs = by_tag[tag]
        if not secs:
            continue
        out.append(f"## {tag}（{len(secs)} 节）")
        out.append("")
        out.append("| § | 标题 | 行范围 | 行数 | 判据 | 覆盖(人工) |")
        out.append("|---|------|:---:|:---:|------|:---:|")
        for s in secs:
            title = s.title.replace("|", "\\|")[:50]
            reasons = "; ".join(s.reasons).replace("|", "\\|")[:50] or "-"
            out.append(f"| {s.number} | {title} | {s.start}-{s.end} | {s.line_count} | {reasons} | ☐ |")
        out.append("")

    return "\n".join(out) + "\n"


def main() -> int:
    if not CLAUDE_MD.exists():
        print(f"ERROR: {CLAUDE_MD} not found", file=sys.stderr)
        return 0
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines(keepends=True)
    sections = parse_sections(lines)
    for s in sections:
        classify(s)

    report = build_report(sections)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")

    counts = {"RULE": 0, "STATUS": 0, "MIXED": 0, "OTHER": 0, "POINTER": 0}
    for s in sections:
        counts[s.tag] += 1
    print(f"Classified {len(sections)} sections: {counts}")
    print(f"Report → {REPORT.relative_to(WORKSPACE)}")

    if "--json" in sys.argv:
        print(json.dumps([
            {"number": s.number, "title": s.title, "tag": s.tag,
             "start": s.start, "end": s.end, "lines": s.line_count}
            for s in sections
        ], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
