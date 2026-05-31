"""
Wiki Health — extensible rules engine for wiki quality checks.

Each rule is an independent check against all wiki pages.
Adding a new check: create a WikiRule subclass in this file (auto-discovered).

Scoring: each rule has a penalty_weight. Final score = max(0, 100 - total_penalty + coverage_bonus).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from core.harness.knowledge.wiki_engine import read_page


# ============================================================
# Data classes
# ============================================================

@dataclass
class WikiIssue:
    check_type: str
    severity: str  # high | medium | low
    page_a: str
    page_b: str = ""
    description: str = ""
    suggestion: str = ""


@dataclass
class WikiHealthReport:
    health_score: int
    total_pages: int
    stats: Dict[str, Any] = field(default_factory=dict)
    issues: List[WikiIssue] = field(default_factory=list)
    checks: List[Dict[str, Any]] = field(default_factory=list)
    link_graph: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "health_score": self.health_score,
            "total_pages": self.total_pages,
            "stats": self.stats,
            "issues": [{
                "check_type": i.check_type,
                "severity": i.severity,
                "page_a": i.page_a,
                "page_b": i.page_b,
                "description": i.description,
                "suggestion": i.suggestion,
            } for i in self.issues],
            "checks": self.checks,
            "link_graph": self.link_graph,
        }


# ============================================================
# Rule base
# ============================================================

class WikiRule:
    """Base class for wiki health check rules."""

    code: str = ""
    severity: str = "low"  # high | medium | low
    penalty_weight: int = 1  # points deducted from health score per issue
    check_name: str = ""

    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:
        """Scan all pages and return issues found."""
        raise NotImplementedError


# ============================================================
# Rules
# ============================================================

class ContradictionCheck(WikiRule):
    code = "contradiction"
    severity = "high"
    penalty_weight = 5
    check_name = "标注矛盾"

    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:
        issues = []
        for title, page in all_pages.items():
            for con in page.get("contradictions", []):
                if con in all_pages:
                    issues.append(WikiIssue(
                        check_type=self.code,
                        severity=self.severity,
                        page_a=title,
                        page_b=con,
                        description="标注矛盾",
                        suggestion=f"合并或协调 '{title}' 和 '{con}' 中的矛盾信息",
                    ))
        return issues


class OrphanCheck(WikiRule):
    code = "orphan"
    severity = "medium"
    penalty_weight = 3
    check_name = "孤立页面"

    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:
        all_linked: Set[str] = set()
        for page in all_pages.values():
            for rel in page.get("related", []):
                all_linked.add(rel)

        issues = []
        for title, page in all_pages.items():
            if title not in all_linked and page.get("related", []):
                issues.append(WikiIssue(
                    check_type=self.code,
                    severity=self.severity,
                    page_a=title,
                    description="孤立页面（无入链）",
                    suggestion=f"在相关页面中添加入站链接指向 '{title}'",
                ))
        return issues


class DeadLinkCheck(WikiRule):
    code = "dead_link"
    severity = "high"
    penalty_weight = 4
    check_name = "死链"

    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:
        all_titles = set(all_pages.keys())
        issues = []
        for title, page in all_pages.items():
            for rel in page.get("related", []):
                if rel not in all_titles:
                    issues.append(WikiIssue(
                        check_type=self.code,
                        severity=self.severity,
                        page_a=title,
                        page_b=rel,
                        description=f"死链（'{rel}' 页面不存在）",
                        suggestion=f"创建 '{rel}' 页面或删除 '{title}' 中的死链接",
                    ))
        return issues


class StaleCheck(WikiRule):
    code = "stale"
    severity = "low"
    penalty_weight = 1
    check_name = "过期页面"

    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:
        stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        issues = []
        for title, page in all_pages.items():
            lu = page.get("last_updated", "")
            if lu and lu < stale_cutoff:
                issues.append(WikiIssue(
                    check_type=self.code,
                    severity=self.severity,
                    page_a=title,
                    description="过期页面（超过30天未更新）",
                    suggestion="检查信息是否仍然准确，或添加reviewed标记",
                ))
        return issues


class ThinContentCheck(WikiRule):
    code = "thin_content"
    severity = "low"
    penalty_weight = 1
    check_name = "内容过短"

    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:
        issues = []
        for title, page in all_pages.items():
            body = page.get("body", "")
            if len(body) < 100:
                issues.append(WikiIssue(
                    check_type=self.code,
                    severity=self.severity,
                    page_a=title,
                    description=f"内容过短（{len(body)} 字符）",
                    suggestion="丰富页面内容，或考虑与相关页面合并",
                ))
        return issues


class NoTagsCheck(WikiRule):
    code = "no_tags"
    severity = "low"
    penalty_weight = 1
    check_name = "缺少标签"

    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:
        issues = []
        for title, page in all_pages.items():
            if not page.get("tags"):
                issues.append(WikiIssue(
                    check_type=self.code,
                    severity=self.severity,
                    page_a=title,
                    description="缺少标签",
                    suggestion="添加相关标签以提高可发现性",
                ))
        return issues


class NoSummaryCheck(WikiRule):
    code = "no_summary"
    severity = "low"
    penalty_weight = 1
    check_name = "缺少摘要"

    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:
        issues = []
        for title, page in all_pages.items():
            if not page.get("summary"):
                issues.append(WikiIssue(
                    check_type=self.code,
                    severity=self.severity,
                    page_a=title,
                    description="缺少摘要",
                    suggestion="添加页面摘要以便快速浏览",
                ))
        return issues


# ============================================================
# Registry
# ============================================================

class WikiHealthRegistry:
    """Runs all wiki health rules and produces a report."""

    def __init__(self):
        self._rules: List[WikiRule] = [cls() for cls in _all_rules()]

    def register(self, rule: WikiRule) -> None:
        self._rules.append(rule)

    def run(self) -> WikiHealthReport:
        from core.harness.knowledge.wiki_engine import _ensure_dirs, _wiki_root

        _ensure_dirs()
        root = _wiki_root()
        all_pages: Dict[str, Dict[str, Any]] = {}

        # Index all pages (shared scan — done once)
        for cat_dir in sorted(root.iterdir()):
            if not cat_dir.is_dir() or cat_dir.name == "contradictions":
                continue
            for md_file in sorted(cat_dir.glob("*.md")):
                page = read_page(md_file.stem, category=cat_dir.name)
                if page:
                    all_pages[page["title"]] = page

        # Stats
        total_pages = len(all_pages)
        categories: Dict[str, int] = {}
        total_tags: Dict[str, int] = {}
        total_related = 0
        pages_with_body = 0
        small_pages = 0

        for page in all_pages.values():
            cat = page.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            for tag in page.get("tags", []):
                total_tags[tag] = total_tags.get(tag, 0) + 1
            total_related += len(page.get("related", []))
            if page.get("body") and len(page["body"]) > 50:
                pages_with_body += 1
            if len(page.get("body", "")) < 200:
                small_pages += 1

        # Run all rules
        all_issues: List[WikiIssue] = []
        checks: List[Dict[str, Any]] = []
        total_penalty = 0

        for rule in self._rules:
            try:
                issues = rule.check(all_pages)
                all_issues.extend(issues)
                count = len(issues)
                penalty = count * rule.penalty_weight
                total_penalty += penalty
                checks.append({
                    "name": rule.check_name or rule.code,
                    "pass": count == 0,
                    "count": count,
                    "severity": rule.severity,
                })
            except Exception:
                checks.append({
                    "name": rule.check_name or rule.code,
                    "pass": True,
                    "count": 0,
                    "severity": rule.severity,
                })

        # Scoring
        base = max(0, 100 - total_penalty)
        coverage = (pages_with_body / max(total_pages, 1)) * 10
        score = min(100, int(base + coverage))

        # Build link graph
        link_graph: Dict[str, List[str]] = {}
        for title, page in all_pages.items():
            link_graph[title] = page.get("related", [])

        return WikiHealthReport(
            health_score=score,
            total_pages=total_pages,
            stats={
                "categories": categories,
                "top_tags": dict(sorted(total_tags.items(), key=lambda x: -x[1])[:15]),
                "total_links": total_related,
                "avg_links_per_page": round(total_related / max(total_pages, 1), 2),
                "pages_with_body": pages_with_body,
                "small_pages": small_pages,
                "orphan_pages": sum(1 for i in all_issues if i.check_type == "orphan"),
                "dead_links": sum(1 for i in all_issues if i.check_type == "dead_link"),
                "stale_pages": sum(1 for i in all_issues if i.check_type == "stale"),
                "thin_pages": sum(1 for i in all_issues if i.check_type == "thin_content"),
                "no_tags": sum(1 for i in all_issues if i.check_type == "no_tags"),
                "no_summary": sum(1 for i in all_issues if i.check_type == "no_summary"),
                "contradictions": sum(1 for i in all_issues if i.check_type == "contradiction"),
            },
            issues=all_issues,
            checks=checks,
            link_graph=link_graph,
        )


def _all_rules() -> List[type]:
    """Collect all WikiRule subclasses defined above."""
    import inspect
    import sys
    rules = []
    current_module = sys.modules[__name__]
    for name in dir(current_module):
        obj = getattr(current_module, name)
        if (isinstance(obj, type)
                and issubclass(obj, WikiRule)
                and obj is not WikiRule
                and not name.startswith("_")):
            rules.append(obj)
    return rules


# ============================================================
# Singleton
# ============================================================

_registry: Optional[WikiHealthRegistry] = None


def get_wiki_registry() -> WikiHealthRegistry:
    global _registry
    if _registry is None:
        _registry = WikiHealthRegistry()
    return _registry
