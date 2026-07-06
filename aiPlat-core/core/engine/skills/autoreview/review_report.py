"""
review_report.py — ReviewReport data model.

Single source of truth for review issue data structures.
Used by: handler.py, report_aggregator.py, auto_fixer.py, scope_governor.py.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ReviewIssue:
    """Single review finding."""
    file: str = ""
    line: int = 0
    severity: str = "P2"           # "P0" | "P1" | "P2"
    category: str = "style"        # "security" | "logic" | "style" | "performance"
    description: str = ""
    fix_suggestion: str = ""
    additions: int = 0             # lines added by fix
    deletions: int = 0             # lines deleted by fix
    engine: str = ""               # source engine (panel mode)
    engines: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file, "line": self.line,
            "severity": self.severity, "category": self.category,
            "description": self.description,
            "fix_suggestion": self.fix_suggestion,
            "engine": self.engine, "engines": self.engines,
        }

    @property
    def fix_size(self) -> int:
        return self.additions - self.deletions


@dataclass
class ReviewReport:
    """Review report — single or panel mode unified output."""

    issues: List[ReviewIssue] = field(default_factory=list)
    common_findings: List[ReviewIssue] = field(default_factory=list)
    unique_findings: Dict[str, List[ReviewIssue]] = field(default_factory=dict)
    scope_violations: List[str] = field(default_factory=list)
    abandoned: bool = False
    abandoned_reason: str = ""
    auto_fixed_count: int = 0
    truncated: bool = False

    # v2.2: 完成证据链
    evidence_cards: List[Dict] = field(default_factory=list)
    engines_used: List[str] = field(default_factory=list)
    reviewed_at: float = 0.0
    target: str = ""
    mode: str = "quick"

    # ── properties ──

    @property
    def p0_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "P0")

    @property
    def p1_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "P1")

    @property
    def p2_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "P2")

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def score(self) -> int:
        """0-100: P0=-20, P1=-5, P2=-1 each."""
        return max(0, 100 - self.p0_count * 20 - self.p1_count * 5 - self.p2_count)

    def is_clean(self) -> bool:
        return self.p0_count == 0 and self.p1_count < 3

    def has_p2_only(self) -> bool:
        return self.p0_count == 0 and self.p1_count == 0 and self.p2_count > 0

    def all_files(self) -> List[str]:
        return list(dict.fromkeys(i.file for i in self.issues if i.file))

    def fixable_p2_issues(self) -> List[ReviewIssue]:
        return [i for i in self.issues
                if i.severity == "P2" and i.fix_suggestion.strip()]

    # ── v2.2: 完成证据链 ──

    def build_evidence(self) -> "ReviewReport":
        """从 self.issues 中自动反推每引擎的发现统计。
        
        无需外部传入监控数据——每条 issue 已标记 engine 来源。
        """
        engine_stats: Dict[str, Dict] = {}
        for issue in self.issues:
            eng = issue.engine or "unknown"
            if eng not in engine_stats:
                engine_stats[eng] = {"issues": 0, "categories": set()}
            engine_stats[eng]["issues"] += 1
            engine_stats[eng]["categories"].add(issue.category)

        self.evidence_cards = [
            {
                "engine": eng,
                "issues": stats["issues"],
                "categories": sorted(stats["categories"]),
            }
            for eng, stats in engine_stats.items()
        ]
        return self

    def clean_evidence(self) -> str:
        """生成 clean 判决的 Markdown 证据摘要。
        仅在 is_clean()=True 时产生有意义的输出。
        """
        if not self.is_clean():
            return ""

        lines = ["## Clean Evidence"]
        if self.reviewed_at:
            import datetime
            dt = datetime.datetime.fromtimestamp(self.reviewed_at).isoformat()
            lines.append(f"**Reviewed at**: {dt}")
        if self.target:
            lines.append(f"**Target**: {self.target} ({self.mode or 'quick'} mode)")
        if self.engines_used:
            lines.append(f"**Engines**: {', '.join(self.engines_used)}")
        lines.append("")

        if self.evidence_cards:
            for card in self.evidence_cards:
                cats = ", ".join(card.get("categories", [])[:3])
                issues = card.get("issues", 0)
                eng = card.get("engine", "?")
                lines.append(f"- **{eng}**: found {issues} issues ({cats})")
        else:
            lines.append("- No issues found by any engine")

        lines.append("")
        lines.append(f"**P0=0, P1={self.p1_count}<3 → clean**")
        return "\n".join(lines)

    # ── scope governor interface ──

    def add_scope_violation(self, reason: str):
        self.scope_violations.append(reason)

    def mark_abandoned(self, reason: str) -> "ReviewReport":
        self.abandoned = True
        self.abandoned_reason = reason
        return self

    # ── factory methods ──

    @staticmethod
    def parse(json_str: str) -> "ReviewReport":
        """Parse LLM JSON output into ReviewReport. Falls back to regex if non-JSON."""
        report = ReviewReport()
        try:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
            if match:
                json_str = match.group(1)
            data = json.loads(json_str)
            if isinstance(data, list):
                data = {"issues": data}
            for d in data.get("issues", []):
                try:
                    report.issues.append(ReviewIssue(
                        file=str(d.get("file", "")),
                        line=int(d.get("line", 0)),
                        severity=str(d.get("severity", "P2")),
                        category=str(d.get("category", "style")),
                        description=str(d.get("description", "")),
                        fix_suggestion=str(d.get("fix_suggestion", "")),
                    ))
                except (ValueError, TypeError):
                    continue
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            report = ReviewReport._fallback_parse(json_str)
        return report

    @staticmethod
    def _fallback_parse(text: str) -> "ReviewReport":
        """Regex fallback when LLM outputs plain text instead of JSON."""
        report = ReviewReport()
        for m in re.finditer(
            r'[\*\s\-]*(\S+?\.\w+):(\d+)\**\s*\[(P[012])\]\s*(?:(\w+):)?\s*(.+)',
            text, re.MULTILINE
        ):
            try:
                report.issues.append(ReviewIssue(
                    file=m.group(1), line=int(m.group(2)),
                    severity=m.group(3),
                    category=m.group(4) or "unknown",
                    description=m.group(5).strip(),
                ))
            except (ValueError, IndexError):
                continue
        return report

    @staticmethod
    def merge(p0_json: str, p2_json: str) -> "ReviewReport":
        """Merge reasoning(P0/P1) + code_gen(P2) outputs."""
        r = ReviewReport()
        r.issues = ReviewReport.parse(p0_json).issues + ReviewReport.parse(p2_json).issues
        return r

    # ── serialization ──

    def to_evaluation_report(self) -> Dict[str, Any]:
        """Adapt to the canonical EvaluationReport schema (CLAUDE.md §10).

        Converges autoreview output onto the same {pass, score, issues} shape
        that `harness.evaluation.workbench.validate_report` validates, so all
        three evaluators share one downstream contract.
        """
        return {
            "pass": self.is_clean(),
            "score": {"overall": round(self.score / 10.0, 2)},
            "issues": [
                {
                    "severity": i.severity,
                    "title": (i.description or "")[:80],
                    "category": i.category,
                    "file": i.file,
                    "line": i.line,
                    "description": i.description,
                    "suggested_fix": i.fix_suggestion,
                }
                for i in self.issues
            ],
            "evaluator": "autoreview",
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score, "clean": self.is_clean(),
            "p0_count": self.p0_count, "p1_count": self.p1_count, "p2_count": self.p2_count,
            "abandoned": self.abandoned, "abandoned_reason": self.abandoned_reason,
            "auto_fixed": self.auto_fixed_count, "truncated": self.truncated,
            "scope_violations": self.scope_violations,
            "issues": [i.to_dict() for i in self.issues],
            "common_findings": [i.to_dict() for i in self.common_findings],
            "unique_findings": {
                engine: [i.to_dict() for i in items]
                for engine, items in self.unique_findings.items()
            },
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Autoreview Report",
            f"**Score**: {self.score}/100  |  **Clean**: {'✅' if self.is_clean() else '❌'}",
            f"**P0**: {self.p0_count}  |  **P1**: {self.p1_count}  |  **P2**: {self.p2_count}",
        ]
        if self.truncated:
            lines.append("⚠️ Diff truncated — partial review only.")
        if self.abandoned:
            lines.append(f"## 🛑 Auto-fix Abandoned: {self.abandoned_reason}")
        if self.scope_violations:
            lines.append("## ⚠️ Scope Violations")
            for v in self.scope_violations:
                lines.append(f"- {v}")
        for sev in ["P0", "P1", "P2"]:
            sis = [i for i in self.issues if i.severity == sev]
            if not sis:
                continue
            lines.append(f"## {sev} ({len(sis)})")
            for i in sis:
                eng = f" [{i.engine}]" if i.engine else ""
                lines.append(f"- **{i.file}:{i.line}** [{i.category}]{eng}: {i.description}")
                if i.fix_suggestion:
                    lines.append(f"  > 💡 {i.fix_suggestion}")
        if self.common_findings:
            lines.append(f"## 🤝 Common Findings ({len(self.common_findings)})")
            for i in self.common_findings[:10]:
                lines.append(f"- **{i.file}:{i.line}** [{i.severity}] — by: {', '.join(i.engines)}")
                lines.append(f"  {i.description}")
        if any(v for v in self.unique_findings.values()):
            lines.append("## 🔍 Unique Findings")
            for eng, items in self.unique_findings.items():
                if items:
                    lines.append(f"- **{eng}**: {len(items)} unique")
        if self.is_clean():
            lines.append(f"\n---\n✅ **autoreview clean**")
            # v2.2: 自动附加完成证据链
            lines.append("")
            lines.extend(self.clean_evidence().split("\n"))
        return "\n".join(lines)
