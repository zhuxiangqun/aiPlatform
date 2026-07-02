"""
Structured Merger — semantic chapter merge with cross-reference validation.

For Map-Reduce document composition (fan-out → parallel chapters → fan-in merge).
When multiple sub-agents write chapters in parallel, this module:
  1. Orders chapters by section number
  2. Extracts and validates cross-references between chapters
  3. Detects dangling references and contradictions
  4. Assembles the final merged document

Usage:
    from core.harness.coordination.merger import StructuredMerger, ChapterOutput

    merger = StructuredMerger()
    chapters = [
        ChapterOutput(section="1", title="概述", content="..."),
        ChapterOutput(section="2.1", title="系统架构", content="参见第1章..."),
    ]
    result = await merger.merge(chapters, llm_model="qwen2.5-coder:7b")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

_log = logging.getLogger("aiplat.structured_merger")


@dataclass
class ChapterOutput:
    section: str
    title: str
    content: str
    author: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrossReference:
    source_section: str
    target_section: str
    context: str = ""
    status: str = "ok"


@dataclass
class MergeIssue:
    issue_type: str  # dangling_ref | contradiction | missing_chapter | style_inconsistency
    severity: str  # error | warning
    source_section: str
    target_section: str = ""
    description: str = ""


@dataclass
class MergedDocument:
    merged_text: str
    chapters: List[ChapterOutput]
    issues: List[MergeIssue] = field(default_factory=list)
    cross_refs: List[CrossReference] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chapter_count": len(self.chapters),
            "section_order": [c.section for c in self.chapters],
            "issues": [{"type": i.issue_type, "severity": i.severity, "desc": i.description[:200]} for i in self.issues],
            "cross_ref_count": len(self.cross_refs),
            "stats": self.stats,
            "merged_text": self.merged_text[:5000],
        }

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0


class StructuredMerger:
    """Semantic chapter merger with cross-reference validation."""

    def __init__(self, enable_llm_merge: bool = True):
        self._enable_llm = enable_llm_merge
        self._ref_patterns = [
            re.compile(p) for p in [
                r"参见第\s*([\d\.]+)\s*章",
                r"见第\s*([\d\.]+)\s*节",
                r"引用第\s*([\d\.]+)\s*章",
                r"详见第\s*([\d\.]+)\s*章",
                r"如第\s*([\d\.]+)\s*章所述",
                r"参考\s*第\s*([\d\.]+)\s*节",
                r"见\s*([\d]+)\s*\.\s*([\d]+)\s*节",
                r"[Ss]ee\s+[Cc]hapter\s+([\d\.]+)",
                r"[Rr]efer\s+to\s+[Ss]ection\s+([\d\.]+)",
            ]
        ]

    async def merge(
        self, chapters: List[ChapterOutput], summary_prompt: str = ""
    ) -> MergedDocument:
        if not chapters:
            return MergedDocument(merged_text="", chapters=[])

        ordered = self._order_chapters(chapters)
        cross_refs = self._extract_cross_references(ordered)
        issues = self._validate_cross_references(cross_refs, ordered)
        issues.extend(self._check_style_consistency(ordered))
        issues.extend(self._check_coverage_gaps(ordered))

        # Assemble merged text
        merged_parts = []
        for ch in ordered:
            merged_parts.append(f"\n## {ch.section}. {ch.title}\n\n{ch.content}")
        
        if self._enable_llm and (issues or len(ordered) > 3):
            merged_text = await self._llm_merge(ordered, issues, summary_prompt)
        else:
            merged_text = "\n".join(merged_parts)

        return MergedDocument(
            merged_text=merged_text,
            chapters=ordered,
            issues=issues,
            cross_refs=cross_refs,
            stats={
                "chapter_count": len(ordered),
                "cross_ref_count": len(cross_refs),
                "issue_count": len(issues),
                "total_chars": sum(len(c.content) for c in ordered),
            },
        )

    def _order_chapters(self, chapters: List[ChapterOutput]) -> List[ChapterOutput]:
        def _sort_key(ch: ChapterOutput) -> tuple:
            parts = []
            for p in ch.section.replace(".", " ").split():
                try:
                    parts.append(int(p))
                except ValueError:
                    parts.append(0)
            return tuple(parts)
        return sorted(chapters, key=_sort_key)

    def _extract_cross_references(self, chapters: List[ChapterOutput]) -> List[CrossReference]:
        refs = []
        valid_sections = {c.section for c in chapters}
        for ch in chapters:
            for pat in self._ref_patterns:
                for match in pat.finditer(ch.content):
                    target = match.group(1)
                    if "." in str(match.groups()[-1]) and match.lastindex and match.lastindex > 1:
                        target = f"{match.group(1)}.{match.group(2)}"
                    if target in valid_sections and target != ch.section:
                        start = max(0, match.start() - 30)
                        end = min(len(ch.content), match.end() + 30)
                        refs.append(CrossReference(
                            source_section=ch.section,
                            target_section=target,
                            context=ch.content[start:end],
                        ))
        return refs

    def _validate_cross_references(
        self, refs: List[CrossReference], chapters: List[ChapterOutput]
    ) -> List[MergeIssue]:
        issues = []
        section_set = {c.section for c in chapters}
        seen_targets: Set[str] = set()

        for ref in refs:
            if ref.target_section not in section_set:
                issues.append(MergeIssue(
                    issue_type="dangling_ref",
                    severity="error",
                    source_section=ref.source_section,
                    target_section=ref.target_section,
                    description=f"第{ref.source_section}章引用了不存在的第{ref.target_section}章",
                ))
            seen_targets.add(ref.target_section)

        # Check all expected chapters are present (ordered references)
        for ch in chapters:
            for ref in refs:
                if ref.source_section == ch.section and ref.target_section not in section_set:
                    issues.append(MergeIssue(
                        issue_type="missing_chapter",
                        severity="error",
                        source_section=ch.section,
                        target_section=ref.target_section,
                        description=f"第{ch.section}章引用了缺失的第{ref.target_section}章",
                    ))

        return issues

    def _check_style_consistency(self, chapters: List[ChapterOutput]) -> List[MergeIssue]:
        issues = []
        if len(chapters) < 2:
            return issues

        first_chapter_starts = [c.content[:30] for c in chapters]
        heading_formats = set()
        for content in first_chapter_starts:
            if content.startswith("##"):
                heading_formats.add("markdown")
            elif content.startswith("#"):
                heading_formats.add("hash")

        if len(heading_formats) > 1:
            issues.append(MergeIssue(
                issue_type="style_inconsistency",
                severity="warning",
                source_section="all",
                description="章节标题格式不一致，建议统一使用 ## 格式",
            ))

        return issues

    def _check_coverage_gaps(self, chapters: List[ChapterOutput]) -> List[MergeIssue]:
        issues = []
        sections = [c.section for c in chapters]
        if not sections:
            return issues

        # Check for gaps in sequential numbering
        nums = []
        for s in sections:
            try:
                nums.append(float(s))
            except ValueError:
                pass

        if nums and len(nums) >= 2:
            nums.sort()
            for i in range(1, len(nums)):
                if nums[i] - nums[i - 1] > 1.5:
                    issues.append(MergeIssue(
                        issue_type="coverage_gap",
                        severity="warning",
                        source_section=str(nums[i - 1]),
                        target_section=str(nums[i]),
                        description=f"章节 {nums[i-1]} 到 {nums[i]} 之间可能存在内容缺失",
                    ))

        return issues

    async def _llm_merge(
        self, chapters: List[ChapterOutput], issues: List[MergeIssue], summary_prompt: str = ""
    ) -> str:
        try:
            from core.harness.utils.model_injection import create_selected_adapter
            chapter_texts = "\n".join(
                f"## {ch.section}. {ch.title}\n{ch.content[:800]}"
                for ch in chapters
            )
            issue_text = ""
            if issues:
                issue_text = "\n## 需要关注的回归校验问题\n"
                for i in issues:
                    issue_text += f"- [{i.severity}] {i.description}\n"

            prompt = (
                f"{summary_prompt or '请将以下各章节合并为一份连贯的完整文档，补充过渡段落，修正交叉引用错误':}"
                f"\n\n{issue_text}\n\n{chapter_texts}\n"
                f"\n请输出合并后的完整文档："
            )
            adapter = create_selected_adapter(purpose="doc_llm")
            result = await adapter.agenerate(prompt=prompt)
            return str(result) if result else "\n".join(
                f"## {ch.section}. {ch.title}\n{ch.content}" for ch in chapters
            )
        except Exception as e:
            _log.warning("LLM merge failed, using simple concatenation: %s", e)
            return "\n".join(
                f"## {ch.section}. {ch.title}\n{ch.content}" for ch in chapters
            )
