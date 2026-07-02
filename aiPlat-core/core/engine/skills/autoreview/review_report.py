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
        return "\n".join(lines)
