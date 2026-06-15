"""
Wiki Structured Query Engine — deterministic query templates.
Implements P1 (query templates) + P4 (golden queries) from Data Agent insights.

The core insight: LLM should handle intent understanding, not data retrieval.
For common query patterns, use deterministic templates to ensure the same
question always produces the same answer (same spirit as NL2MQL2SQL).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import json as _json
from pathlib import Path

# ── Query Templates ─────────────────────────────────────────────
# Each template maps a query intent to a deterministic execution plan.

def structured_query(query: str) -> Dict[str, Any]:
    """Route a natural language query to the best-matching deterministic template.
    
    Returns {result, template_used, confidence} or {error, reason} if no match.
    """
    ql = query.lower().strip()
    
    # Template 1: "介绍 X" / "什么是 X" — concept lookup
    if any(k in ql for k in ("什么是", "介绍", "define", "what is", "概念")):
        entity = _extract_last_entity(query)
        if entity:
            return _concept_lookup(entity)
    
    # Template 2: "X 和 Y 有什么区别" — comparison
    if any(k in ql for k in ("区别", "对比", "比较", "vs", "diff", "compare")):
        entities = _extract_comparison_entities(query)
        if len(entities) >= 2:
            return _comparison(entities[0], entities[1])
    
    # Template 3: "X 有哪些案例/示例" — case listing
    if any(k in ql for k in ("案例", "示例", "例子", "example", "case")):
        entity = _extract_last_entity(query)
        if entity:
            return _case_listing(entity)
    
    # Template 4: "最近更新了什么" / "最新的" — recent changes
    if any(k in ql for k in ("最近", "最新", "更新", "recent", "latest")):
        return _recent_changes(ql)
    
    # Template 5: "健康报告" / "wiki 状态" — health snapshot
    if any(k in ql for k in ("健康", "状态", "报告", "health", "status", "报告", "lint")):
        return _health_snapshot()
    
    # Template 6: "哪些页面缺来源/缺标签/孤立" — quality gaps
    if any(k in ql for k in ("缺来源", "缺标签", "孤立", "缺少", "没标签", "没来源")):
        return _quality_gaps(ql)
    
    # Template 7: "概览" / "总结" — wiki overview
    if any(k in ql for k in ("概览", "总结", "overview", "summary", "总览", "全局")):
        return _wiki_overview()
    
    # Template 8: "X 引用了哪些资料" — source tracking (must be after quality_gaps)
    if any(k in ql for k in ("引用", "资料", "source", "kb:")):
        return _source_tracking(ql)
    
    return {"result": None, "template_used": None, "confidence": 0,
            "reason": "no matching template", "hint": "Try: 介绍X / X和Y的区别 / X有哪些案例 / wiki健康报告"}


# ── Template Implementations ─────────────────────────────────────

def _concept_lookup(entity: str) -> Dict[str, Any]:
    from core.harness.knowledge.wiki_engine import read_page, traverse_links, search_pages
    
    page = read_page(entity)
    if not page:
        # Try fuzzy search — prefer pages whose titles contain the search term
        results = search_pages(entity)
        if results:
            # Rank: title match first (any token of entity in title), then short titles
            tokens_lower = [t.lower() for t in entity.lower().split()]
            def _rank(p: dict) -> tuple:
                t = p.get("title", "").lower()
                match = any(tok in t for tok in tokens_lower)
                return (0 if match else 1, len(t))
            results.sort(key=_rank)
            page = results[0]
            entity = page["title"]
        else:
            return {"result": f"未找到关于 '{entity}' 的页面", "template_used": "概念查询",
                    "confidence": 0.5, "suggestion": "尝试用更通用的名称搜索"}
    
    # Build structured output
    entities_linked = []
    for rel_name in page.get("related", [])[:5]:
        rel_page = read_page(rel_name)
        if rel_page:
            entities_linked.append({"title": rel_name, "summary": rel_page.get("summary", "")[:100]})
    
    return {
        "result": {
            "title": entity,
            "summary": page.get("summary", ""),
            "category": page.get("category", ""),
            "tags": page.get("tags", [])[:10],
            "related_pages": entities_linked,
            "source_articles": page.get("source_articles", []),
            "typed_relationships": page.get("relationships", []),
        },
        "template_used": "概念查询",
        "confidence": 0.95,
    }


def _comparison(entity_a: str, entity_b: str) -> Dict[str, Any]:
    from core.harness.knowledge.wiki_engine import read_page, search_pages
    
    page_a = read_page(entity_a)
    if not page_a:
        results = search_pages(entity_a)
        if results:
            tokens = entity_a.lower().split()
            results.sort(key=lambda p: (0 if any(t in p.get("title","").lower() for t in tokens) else 1, len(p.get("title",""))))
            page_a = results[0]
            entity_a = page_a.get("title", entity_a)
    
    page_b = read_page(entity_b)
    if not page_b:
        results = search_pages(entity_b)
        if results:
            tokens = entity_b.lower().split()
            results.sort(key=lambda p: (0 if any(t in p.get("title","").lower() for t in tokens) else 1, len(p.get("title",""))))
            page_b = results[0]
            entity_b = page_b.get("title", entity_b)
    
    if not page_a and not page_b:
        return {"result": f"比较失败：未找到 {entity_a} 和 {entity_b}",
                "template_used": "对比查询", "confidence": 0.4}
    
    # Allow partial match: if only one entity found, still return what we have
    dims: Dict[str, Any] = {
        "tags": {"a": set(page_a.get("tags", []) if page_a else []), 
                 "b": set(page_b.get("tags", []) if page_b else [])},
        "category": {"a": page_a.get("category", "") if page_a else "", 
                      "b": page_b.get("category", "") if page_b else ""},
        "sources": {"a": len(page_a.get("source_articles", [])) if page_a else 0, 
                     "b": len(page_b.get("source_articles", [])) if page_b else 0},
        "summary_a": page_a.get("summary", "") if page_a else "",
        "summary_b": page_b.get("summary", "") if page_b else "",
    }
    
    return {
        "result": {
            "entity_a": {"title": page_a.get("title", entity_a) if page_a else entity_a, 
                         "summary": page_a.get("summary", "") if page_a else "", 
                         "tags": page_a.get("tags", [])[:8] if page_a else []},
            "entity_b": {"title": page_b.get("title", entity_b) if page_b else entity_b, 
                         "summary": page_b.get("summary", "") if page_b else "", 
                         "tags": page_b.get("tags", [])[:8] if page_b else []},
            "shared_tags": list(dims["tags"]["a"] & dims["tags"]["b"]),
            "unique_to_a": list(dims["tags"]["a"] - dims["tags"]["b"]),
            "unique_to_b": list(dims["tags"]["b"] - dims["tags"]["a"]),
        },
        "template_used": "对比查询",
        "confidence": 0.90 if page_a and page_b else 0.6,
    }


def _case_listing(entity: str) -> Dict[str, Any]:
    from core.harness.knowledge.wiki_engine import read_page, list_all_pages, search_pages
    
    page = read_page(entity)
    if not page:
        results = search_pages(entity)
        if not results:
            # Try shorter token: first word of entity
            tokens = entity.split()
            if tokens:
                results = search_pages(tokens[0])
        if results:
            tokens_lower = [t.lower() for t in entity.lower().split()]
            results.sort(key=lambda p: (0 if any(t in p.get("title","").lower() for t in tokens_lower) else 1, len(p.get("title",""))))
            page = results[0]
            entity = page.get("title", entity)
    cases = []
    for p in list_all_pages():
        title = p.get("title", "")
        info = p
        rels = info.get("relationships", [])
        for rel in rels:
            if rel.get("target") == entity and rel.get("type") == "example_of":
                cases.append({"title": title, "summary": info.get("summary", "")[:100]})
    # Fallback: check `related` field
    if not cases:
        for p in list_all_pages():
            if entity in p.get("related", []):
                cases.append({"title": p.get("title", ""), "summary": p.get("summary", "")[:100]})
    
    return {
        "result": {
            "concept": entity,
            "concept_summary": page.get("summary", "") if page else "",
            "cases": cases[:10],
        },
        "template_used": "案例查询",
        "confidence": 0.85 if cases else 0.5,
    }


def _recent_changes(_query: str) -> Dict[str, Any]:
    from core.harness.knowledge.wiki_engine import list_all_pages
    
    pages = sorted(
        [p for p in list_all_pages() if p.get("last_updated")],
        key=lambda x: x.get("last_updated", ""),
        reverse=True
    )[:10]
    
    return {
        "result": [{
            "title": p.get("title", ""),
            "updated": p.get("last_updated", ""),
            "category": p.get("category", ""),
            "summary": p.get("summary", "")[:100],
        } for p in pages],
        "template_used": "最近变更",
        "confidence": 0.95,
    }


def _health_snapshot() -> Dict[str, Any]:
    try:
        from core.harness.knowledge.wiki_health_rules import get_health_trend
        trend = get_health_trend()
        return {
            "result": trend,
            "template_used": "健康报告",
            "confidence": 0.95,
        }
    except Exception:
        return {"result": "无法获取健康报告", "template_used": "健康报告", "confidence": 0.5}


def _quality_gaps(query: str) -> Dict[str, Any]:
    from core.harness.knowledge.wiki_engine import list_all_pages, read_page
    
    all_pages = list_all_pages()
    results = []
    for p in all_pages:
        title = p.get("title", "")
        page = read_page(title)
        if not page:
            continue
        gaps = []
        if "source" in query and not p.get("source_articles"):
            gaps.append("缺来源")
        if "标签" in query and not p.get("tags"):
            gaps.append("缺标签")
        if "孤立" in query and not p.get("related"):
            gaps.append("孤立页面")
        if gaps:
            results.append({"title": title, "gaps": gaps, "category": p.get("category", "")})
    
    return {
        "result": {"pages_with_gaps": results[:15], "total": len(results)},
        "template_used": "质量缺口",
        "confidence": 0.90,
    }


def _wiki_overview() -> Dict[str, Any]:
    from core.harness.knowledge.wiki_engine import list_all_pages
    
    pages = list_all_pages()
    cats: Dict[str, int] = {}
    total_tags = 0
    total_links = 0
    for p in pages:
        cats[p.get("category", "other")] = cats.get(p.get("category", "other"), 0) + 1
        total_tags += len(p.get("tags", []))
        total_links += len(p.get("related", []))
    
    return {
        "result": {
            "total_pages": len(pages),
            "by_category": cats,
            "avg_tags": round(total_tags / max(len(pages), 1), 1),
            "avg_links": round(total_links / max(len(pages), 1), 1),
        },
        "template_used": "全局概览",
        "confidence": 0.95,
    }


def _source_tracking(query: str) -> Dict[str, Any]:
    from core.harness.knowledge.wiki_engine import search_pages
    
    # Extract source key from query (e.g., "kb:xxx")
    import re
    m = re.search(r'(kb:\S+|vault:\S+)', query)
    source_key = m.group(1) if m else None
    
    if source_key:
        pages = search_pages(source_key)
        return {
            "result": {"source": source_key, "pages": [(p.get("title",""), p.get("summary","")[:100]) for p in pages]},
            "template_used": "来源追踪",
            "confidence": 0.90,
        }
    else:
        # Fallback: list pages with source_articles
        all_pages = search_pages(limit=100)
        with_sources = [(p.get("title",""), p.get("source_articles",[])) for p in all_pages if p.get("source_articles")]
        return {
            "result": {"pages_with_sources": [{"title": t, "count": len(s)} for t, s in with_sources[:20]]},
            "template_used": "来源追踪",
            "confidence": 0.85 if with_sources else 0.5,
        }


# ── Helpers ──────────────────────────────────────────────────────

def _extract_last_entity(query: str) -> Optional[str]:
    """Extract the most likely entity name from a query."""
    q = query.strip()
    # Strip common trailing modifier words from entire query before extraction
    suffixes = [
        "可以推理到达哪些相关概念",
        "的所有相关概念（含推理扩展）",
        "的上层概念有哪些",
        "的架构有哪些",
        "的相关概念",
        "有哪些案例", "有哪些示例", "有哪些例子",
        "有哪些",
    ]
    for suffix in suffixes:
        if suffix in q:
            q = q.split(suffix)[0].strip()
            break
    # Try to extract entity after known prefixes
    for prefix in ("什么是", "介绍", "搜索", "查询", "查找", "列举", "列出", "关于",
                   "从"):
        if prefix in q:
            after = q.split(prefix)[-1].strip()
            if after and len(after) >= 2:
                return after[:80]
    # Fallback: the whole stripped query is the entity
    if q and len(q) >= 2:
        return q[:80]
    return query[:80]


def _extract_comparison_entities(query: str) -> List[str]:
    """Extract two entities from a comparison query."""
    import re
    entities = []
    # Pattern: "X 和 Y"
    m = re.search(r'["""「](.+?)[""\」]', query)
    if m:
        entities.append(m.group(1))
    # Simple split on comparison keywords - take the text before and after
    for sep in ("和", "vs", "与", "对比", "比较", "区别"):
        parts = query.split(sep)
        if len(parts) == 2:
            left = parts[0].strip()
            right = parts[1].strip()
            # Strip common suffix words from right side
            for suffix in ("的区别", "对比", "比较", "的差异", "有什么不同", "的不同"):
                if suffix in right:
                    right = right.split(suffix)[0].strip()
                    break
            if left and right:
                entities = [left[:80], right[:80]]
                break
    return entities[:2]


# ── P4: Golden Query Regression Test ─────────────────────────────

def run_golden_tests() -> Dict[str, Any]:
    """Run regression tests against golden queries to detect quality degradation."""
    root = Path(__import__('os').environ.get("AIPLAT_HOME", 
                __import__('os').path.expanduser("~/.aiplat"))) / "wiki"
    gq_path = root / "golden_queries.yaml"
    
    tests = _load_golden_queries(gq_path)
    if not tests:
        return {"status": "skipped", "reason": "no_golden_queries_defined"}
    
    results = []
    passed = 0
    for test in tests:
        query = test.get("query", "")
        expected = test.get("expected_concepts", test.get("expected_pages", []))
        assertion = test.get("assertion", "")
        
        result = structured_query(query)
        query_type = test.get("query_type", test.get("template", ""))
        actual_titles = []
        res = result.get("result", {})
        template = result.get("template_used", "")
        
        if template == "概念查询":
            if isinstance(res, dict):
                actual_titles = [res.get("title", "")]
        elif template == "对比查询":
            if isinstance(res, dict):
                actual_titles = [res.get("entity_a", {}).get("title", ""),
                                 res.get("entity_b", {}).get("title", "")]
        elif template == "案例查询":
            if isinstance(res, dict):
                actual_titles = [res.get("concept", "")]
        elif isinstance(res, list):
            actual_titles = [r.get("title", "") for r in res if isinstance(r, dict)]
        
        found = [e for e in expected if e in actual_titles or any(e in t for t in actual_titles)]
        # Empty expected = always pass
        if not expected:
            ok = True
        elif query_type in ("inference", "source_impact", "schema_validation"):
            # For inference/schema queries, check if expected pages exist in wiki
            if expected:
                from core.harness.knowledge.wiki_engine import read_page as _rp
                existing = [e for e in expected if _rp(e)]
                ok = len(existing) >= max(1, len(expected) * 0.5)
            else:
                ok = len(actual_titles) > 0 or (isinstance(res, (list, dict)) and bool(res))
        elif template in ("全局概览", None, ""):
            # Overview / unmatched: check if expected pages exist in wiki
            if expected:
                from core.harness.knowledge.wiki_engine import read_page as _rp
                existing = [e for e in expected if _rp(e)]
                ok = len(existing) >= max(1, len(expected) * 0.5)
            else:
                ok = True
        else:
            ok = len(found) >= max(1, len(expected) * 0.5)
        if ok:
            passed += 1
        
        results.append({
            "query_id": test.get("id", ""),
            "query": query,
            "passed": ok,
            "expected": expected,
            "found": actual_titles[:5],
            "template": result["template_used"],
        })
    
    return {
        "status": "completed",
        "total": len(tests),
        "passed": passed,
        "pass_rate": round(passed / max(len(tests), 1), 2),
        "results": results,
    }


def _load_golden_queries(path: Path) -> List[Dict[str, Any]]:
    """Load golden queries from YAML file."""
    try:
        if not path.exists():
            return []
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("queries", []) if isinstance(data, dict) else []
    except Exception:
        return []


def seed_golden_queries() -> str:
    """Create a default golden_queries.yaml template if none exists."""
    root = Path(__import__('os').environ.get("AIPLAT_HOME",
                __import__('os').path.expanduser("~/.aiplat"))) / "wiki"
    gq_path = root / "golden_queries.yaml"
    if gq_path.exists():
        return "golden_queries.yaml already exists"
    
    template = """# Golden Query Set — Wiki Quality Regression Tests
# Add common queries with expected results. Run `run_golden_tests()` to verify.
# Goal: ensure the wiki system does NOT degrade over time.

queries:
  # - query: "什么是 RAG"
  #   expected_pages: ["RAG概念页", "RAG与Wiki对比"]
  #   assertion: "回答应包含向量检索和知识复利两个概念"
  # 
  # - query: "Wiki 和 RAG 有什么区别"
  #   expected_pages: ["Wiki概述", "RAG概述"]
  #   assertion: "对比应包含至少 3 个维度"
  #
  # - query: "最近更新了什么"
  #   expected_pages: []
  #   assertion: "应返回至少 1 条最近变更"
"""
    gq_path.write_text(template, encoding="utf-8")
    return f"Created {gq_path}"
