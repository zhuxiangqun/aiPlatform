"""

Wiki Health — extensible rules engine for wiki quality checks.



Each rule is an independent check against all wiki pages.

Adding a new check: create a WikiRule subclass in this file (auto-discovered).



Scoring: each rule has a penalty_weight. Final score = max(0, 100 - total_penalty + coverage_bonus).

"""



from __future__ import annotations

import logging

import os



from dataclasses import dataclass, field

from datetime import datetime, timedelta, timezone

from typing import Any, Dict, List, Optional, Set





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

        collection_id = "default"

        

        # ── Phase 1: detect ghost pages via batch cleanup (dry_run) ──

        ghost_titles: set = set()

        try:

            from core.harness.knowledge.wiki_engine import cleanup_ghost_pages

            result = cleanup_ghost_pages(collection_id=collection_id, dry_run=True)

            ghost_titles = set(result.get("ghosts_found", []))

        except Exception:

            logging.getLogger(__name__).debug('check failed', exc_info=True)
        

        for title, page in all_pages.items():

            body = page.get("body", "")

            

            # Ghost pages: search index entries with no stored data

            if title in ghost_titles:

                issues.append(WikiIssue(

                    check_type=self.code,

                    severity="low",

                    page_a=title,

                    description="幽灵页面（搜索索引残影，无存储数据）",

                    suggestion=f"运行 POST /api/core/wiki/cleanup-ghosts 批量清理，或忽略此条",

                ))

                continue

            

            # search_pages returns truncated bodies. Use read_page() for full content.

            if len(body) < 20:

                try:

                    from core.harness.knowledge.wiki_engine import read_page

                    full_page = read_page(title, collection_id=page.get("collection_id", collection_id))

                    if full_page:

                        body = full_page.get("body", body)

                except Exception:

                    logging.getLogger(__name__).debug('check failed', exc_info=True)
            

            if len(body) < 20:

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





class SemanticContradictionCheck(WikiRule):

    """LLM-powered contradiction detection using embedding similarity.



    Flags pages with very similar semantic content (cosine sim >= 0.85)

    that are NOT already marked as contradictions. The idea: if two

    pages discuss the same topic but are in different categories

    (e.g., entities vs topics), they may contain conflicting claims.

    """



    code = "semantic_contradiction"

    severity = "medium"

    penalty_weight = 3

    check_name = "语义矛盾候选"



    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:

        issues = []

        pages = [(t, p) for t, p in all_pages.items() if p.get("category") != "contradictions"]

        if len(pages) < 2:

            return issues



        try:

            from core.harness.knowledge.embedder import embed_text_semantic

        except ImportError:

            return issues



        existing_contradictions: set = set()

        for title, page in all_pages.items():

            for c in (page.get("contradictions") or []):

                if isinstance(c, str):

                    existing_contradictions.add(tuple(sorted([title, c])))



        for i in range(len(pages)):

            for j in range(i + 1, len(pages)):

                t1, p1 = pages[i]

                t2, p2 = pages[j]

                # Only flag cross-category pairs (entity vs topic = potential conflict)

                if p1.get("category") == p2.get("category"):

                    continue

                # Skip already-marked contradictions

                if tuple(sorted([t1, t2])) in existing_contradictions:

                    continue

                b1 = p1.get("body", "")[:2000]

                b2 = p2.get("body", "")[:2000]

                if not b1 or not b2:

                    continue

                try:

                    sim = embed_text_semantic(b1, b2)

                    if sim >= 0.85:

                        issues.append(WikiIssue(

                            check_type=self.code,

                            severity=self.severity,

                            page_a=t1,

                            page_b=t2,

                            description=f"语义相似度 {sim:.2f}，可能包含矛盾信息",

                            suggestion=f"'{t1}' 和 '{t2}' 讨论相似主题但处于不同分类，建议检查是否存在冲突并添加交叉引用",

                        ))

                except Exception:

                    continue

        return issues





class DuplicateCheck(WikiRule):

    """Detect pages with highly similar content (potential duplicates).



    Uses embedding cosine similarity with a threshold of 0.90.

    Pages in the same category with similarity >= threshold are

    flagged as potential duplicates that should be merged.

    """



    code = "duplicate_content"

    severity = "medium"

    penalty_weight = 2

    check_name = "内容重复"



    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:

        try:

            from core.harness.knowledge.wiki_engine import detect_duplicate_pages

            dupes = detect_duplicate_pages(threshold=0.90)

        except Exception:

            return []



        # Per-layer cap to prevent one noisy category from flooding results

        layer_cap: Dict[str, int] = {"L1_content": 10, "L2_ontology": 5, "L3_structural": 5, "L4_evidence": 5}

        layer_count: Dict[str, int] = {}

        issues = []

        for d in dupes:

            layer = d.get("layer", "")

            lc = layer_count.get(layer, 0)

            if lc >= layer_cap.get(layer, 10):

                continue

            layer_count[layer] = lc + 1

            issues.append(WikiIssue(

                check_type=self.code,

                severity=self.severity,

                page_a=d["page_a"],

                page_b=d["page_b"],

                description=f"相似度 {d['similarity']:.2f}，疑似重复",

                suggestion=d.get("suggestion", "建议考虑合并或明确区分这两个页面"),

            ))

        return issues





class OntologyValidationRule(WikiRule):

    """Validate the knowledge base against ontology axioms A1-A7.



    Uses the A-Box builder and validator to check:

    - Concept pages without KB sources (A1)

    - Asymmetric contradiction declarations (A3)

    - parentOf cycles (A4)

    - Source pages citing Wiki pages (A5)

    - Invalid KB document references (A6)

    """



    code = "ontology_validation"

    severity = "high"

    penalty_weight = 5

    check_name = "本体一致性验证"



    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:

        issues = []

        try:

            from core.harness.knowledge.knowledge_validator import compute_ontology_metrics



            # Reuse cached metrics (avoids duplicate A-Box build + validate)

            metrics = compute_ontology_metrics(collection_id=self.collection_id)

            consistency = metrics.get("consistency", {})

            score = consistency.get("score", 100)

            errors = consistency.get("errors", 0)

            warnings = consistency.get("warnings", 0)



            # If score is perfect, no issues to report

            if score >= 100 and errors == 0 and warnings == 0:

                return issues



            # Build full A-Box only if metrics indicate violations (for detailed issue listing)

            from core.harness.knowledge.knowledge_abox_builder import build_abox

            from core.harness.knowledge.knowledge_validator import validate as onto_validate



            onto = build_abox(collection_id=self.collection_id)

            report = onto_validate(onto)



            for v in report.violations:

                severity = v.severity

                page_a = v.entities[0] if v.entities else "unknown"

                page_b = v.entities[1] if len(v.entities) > 1 else None



                # Clean URI prefixes for display

                page_a = page_a.replace("http://aiplat.local/knowledge#", "")

                if page_b:

                    page_b = page_b.replace("http://aiplat.local/knowledge#", "")



                issues.append(WikiIssue(

                    check_type=self.code,

                    severity=severity,

                    page_a=page_a,

                    page_b=page_b,

                    description=f"[{v.axiom_id}] {v.description}",

                    suggestion=v.recommendation,

                ))

        except Exception as e:

            logging.debug(str(e), exc_info=True)



        return issues





class OntologyCoverageCheck(WikiRule):

    """Check how many Wiki pages are correctly classified under T-Box CLASSES."""



    code = "ontology_coverage"

    severity = "medium"

    penalty_weight = 2

    check_name = "本体覆盖度"



    def check(self, all_pages: Dict[str, Dict[str, Any]]) -> List[WikiIssue]:

        from core.harness.knowledge.knowledge_ontology import CLASSES



        issues = []

        classified = 0

        unclassified = 0



        # Collect all allowed categories from T-Box

        all_allowed: Set[str] = set()

        for cls in CLASSES:

            for cat in cls.allowed_categories:

                all_allowed.add(cat)



        for title, page in all_pages.items():

            category = page.get("category", "")

            if not category:

                unclassified += 1

                issues.append(WikiIssue(

                    check_type=self.code, severity=self.severity,

                    page_a=title, description=f"页面 '{title}' 缺少 category 字段",

                    suggestion="在页面 frontmatter 中添加 category 字段",

                ))

            elif category not in all_allowed:

                unclassified += 1

                issues.append(WikiIssue(

                    check_type=self.code, severity=self.severity,

                    page_a=title,

                    description=f"页面分类 '{category}' 未在 T-Box CLASSES 中注册",

                    suggestion=f"在 knowledge_ontology.py 的 CLASSES 中添加 allowed_categories=['{category}']",

                ))

            else:

                classified += 1



        total = classified + unclassified

        if total > 0:

            coverage_pct = round(classified / total * 100, 1)

            if coverage_pct < 80:

                issues.append(WikiIssue(

                    check_type=self.code, severity="high",

                    page_a="整体",

                    description=f"本体覆盖度: {coverage_pct}% ({classified}/{total} 页面已分类)",

                    suggestion=f"将 {unclassified} 个未分类页面的 category 注册到 T-Box CLASSES",

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

        from core.harness.knowledge.wiki_engine import read_page, _ensure_dirs, _wiki_root



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



        report = WikiHealthReport(

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



        # ── Persist health history for trend tracking ──

        try:

            _save_health_snapshot(report)

        except Exception as e:

            logging.debug(str(e), exc_info=True)



        return report





def _save_health_snapshot(report: WikiHealthReport) -> None:

    """Save a health report snapshot for trend tracking (keeps last 50)."""

    import json as _json

    from pathlib import Path

    root = Path(os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "wiki"

    history_file = root / "health_history.json"



    # Load existing history

    existing: list = []

    try:

        if history_file.exists():

            with open(history_file, "r", encoding="utf-8") as f:

                existing = _json.load(f)

    except Exception as e:

        logging.debug(str(e), exc_info=True)



    snapshot = {

        "timestamp": datetime.now(timezone.utc).isoformat(),

        "score": report.health_score,

        "grade": report.grade,

        "total_pages": report.total_pages,

        "issues_total": len(report.issues),

        "issues_by_type": {},

        "checks": report.checks,

    }

    # Aggregate issue counts by type

    for issue in report.issues:

        t = issue.check_type

        snapshot["issues_by_type"][t] = snapshot["issues_by_type"].get(t, 0) + 1



    existing.insert(0, snapshot)

    existing = existing[:50]



    try:

        history_file.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    except Exception as e:

        logging.debug(str(e), exc_info=True)





def get_health_trend() -> Dict[str, Any]:

    """Read health history and compute trend metrics.



    Returns:

        - history: list of recent snapshots (last 10)

        - trend: {score_delta, grade_trend, direction} comparing last 2 snapshots

        - best: highest score + when

    """

    import json as _json

    import os

    from pathlib import Path

    root = Path(os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "wiki"

    history_file = root / "health_history.json"



    entries: list = []

    try:

        if history_file.exists():

            with open(history_file, "r", encoding="utf-8") as f:

                entries = _json.load(f)

    except Exception as e:

        logging.debug(str(e), exc_info=True)



    recent = entries[:10]



    # Score trend (comparing latest 2)

    score_delta = 0

    grade_trend = "stable"

    if len(recent) >= 2:

        score_delta = recent[0].get("score", 0) - recent[1].get("score", 0)

        if score_delta > 0:

            grade_trend = "improving"

        elif score_delta < 0:

            grade_trend = "declining"

        else:

            grade_trend = "stable"



    best_entry = max(entries, key=lambda e: e.get("score", 0)) if entries else {"score": None}



    return {

        "history": recent,

        "trend": {

            "score_delta": score_delta,

            "grade_trend": grade_trend,

            "direction": "↑" if score_delta > 0 else "↓" if score_delta < 0 else "→",

        },

        "best": {"score": best_entry.get("score"), "timestamp": best_entry.get("timestamp")},

        "total_snapshots": len(entries),

    }





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

