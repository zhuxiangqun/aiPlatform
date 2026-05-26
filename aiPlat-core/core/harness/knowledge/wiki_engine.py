"""
Wiki Engine — persistent, LLM-maintained markdown knowledge base.

Operations: search (by title/tag/link), traverse (follow [[links]]),
read/write pages, detect contradictions.

Wiki root: ~/.aiplat/wiki/
Directory structure:
  entities/          # Entity pages (concepts, people, projects)
  topics/            # Topic summaries (cross-entity analyses)
  contradictions/    # Detected contradictions (auto-marked by LLM)
  schema.yml         # Wiki structure rules
  index.json         # Global page index
"""

from __future__ import annotations

import os
import re
import json as _json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Configuration ──────────────────────────────────────────────

def _wiki_root() -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    return Path(home) / "wiki"

def _ensure_dirs():
    root = _wiki_root()
    for d in ["entities", "topics", "contradictions"]:
        (root / d).mkdir(parents=True, exist_ok=True)
    idx = root / "index.json"
    if not idx.exists():
        idx.write_text(_json.dumps({"pages": {}, "last_updated": ""}, indent=2))
    schema = root / "schema.yml"
    if not schema.exists():
        schema.write_text("# Wiki Schema — customize wiki structure rules\n"
                         "categories:\n"
                         "  - entities     # People, projects, concepts\n"
                         "  - topics       # Cross-entity analysis\n"
                         "  - contradictions  # Knowledge conflicts\n"
                         "template:\n"
                         "  fields:\n"
                         "    - title\n"
                         "    - summary\n"
                         "    - related_pages\n"
                         "    - contradictions\n"
                         "    - last_updated\n"
                         "    - source_articles\n")

# ── Page read/write ────────────────────────────────────────────

FRONTMATTER_FIELDS = {
    "title": "",
    "category": "entity",
    "tags": [],
    "related": [],
    "contradictions": [],
    "source_articles": [],
    "last_updated": "",
    "summary": "",
}


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from markdown wiki page."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2].strip()
    fm: Dict[str, Any] = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip().strip("'\"")
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
        else:
            fm[key] = val
    for k, default in FRONTMATTER_FIELDS.items():
        if k not in fm:
            fm[k] = default
    return fm, body


def read_page(title_or_path: str, *, category: str = "entities") -> Optional[Dict[str, Any]]:
    """Read a wiki page. Returns {title, category, tags, body, fm, path} or None."""
    _ensure_dirs()
    root = _wiki_root()
    name = re.sub(r"[<>:\"/\\|?*]", "_", title_or_path)[:120]
    # Try exact match first
    for cat in [category, "entities", "topics", "contradictions"]:
        p = root / cat / f"{name}.md"
        if p.exists():
            text = p.read_text(encoding="utf-8")
            fm, body = _parse_frontmatter(text)
            return {"title": fm.get("title", name), "category": cat, "tags": fm.get("tags", []),
                    "related": fm.get("related", []), "contradictions": fm.get("contradictions", []),
                    "source_articles": fm.get("source_articles", []),
                    "last_updated": fm.get("last_updated", ""), "summary": fm.get("summary", ""),
                    "body": body, "fm": fm, "path": str(p)}
    return None


def write_page(title: str, body: str, *, category: str = "entities", tags: List[str] = None,
               related: List[str] = None, contradictions: List[str] = None,
               source_articles: List[str] = None, summary: str = "") -> str:
    """Create or update a wiki page. Returns the file path."""
    _ensure_dirs()
    root = _wiki_root()
    name = re.sub(r"[<>:\"/\\|?*]", "_", title)[:120]
    existing = read_page(title, category=category)
    now = datetime.utcnow().isoformat()

    # Merge with existing if updating
    if existing:
        tags = list(set((existing.get("tags") or []) + (tags or [])))
        related = list(set((existing.get("related") or []) + (related or [])))
        contradictions = list(set((existing.get("contradictions") or []) + (contradictions or [])))
        source_articles = list(set((existing.get("source_articles") or []) + (source_articles or [])))
        summary = summary or existing.get("summary", "")

    fm_lines = [
        f"title: {title}",
        f"category: {category}",
        f"tags: [{', '.join(tags or [])}]",
        f"related: [{', '.join(related or [])}]",
        f"contradictions: [{', '.join(contradictions or [])}]",
        f"source_articles: [{', '.join(source_articles or [])}]",
        f"last_updated: {now}",
        f"summary: {summary[:500]}",
    ]

    content = "---\n" + "\n".join(fm_lines) + "\n---\n\n" + body
    p = root / category / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

    # Update index
    _update_index(title, category, tags or [], related or [])
    return str(p)


def _update_index(title: str, category: str, tags: List[str], related: List[str]):
    idx_path = _wiki_root() / "index.json"
    try:
        idx = _json.loads(idx_path.read_text(encoding="utf-8"))
    except Exception:
        idx = {"pages": {}, "last_updated": ""}
    idx["pages"][title] = {"category": category, "tags": tags, "related": related,
                             "last_updated": datetime.utcnow().isoformat()}
    idx["last_updated"] = datetime.utcnow().isoformat()
    idx_path.write_text(_json.dumps(idx, indent=2, ensure_ascii=False))


def update_page(title: str, **kwargs) -> bool:
    u"""Update specific frontmatter fields of an existing wiki page, preserving others."""
    existing = None
    for cat_dir in _wiki_root().iterdir():
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        test = read_page(title, category=cat_dir.name)
        if test:
            existing = test
            break
    if not existing:
        return False

    for key in ("summary", "category", "tags", "related", "contradictions", "source_articles"):
        if key in kwargs and kwargs[key] is not None:
            existing[key] = kwargs[key]

    name = kwargs.get("title", title)
    if name != title:
        existing["title"] = name

    write_page(existing["title"], existing.get("body", ""),
               category=existing.get("category", "entities"),
               tags=existing.get("tags", []),
               related=existing.get("related", []),
               summary=existing.get("summary", ""),
               contradictions=existing.get("contradictions", []),
               source_articles=existing.get("source_articles", []))
    return True


# ── Search ─────────────────────────────────────────────────────

def search_pages(query: str = "", *, tags: List[str] = None, category: str = "",
                  limit: int = 20) -> List[Dict[str, Any]]:
    """Search wiki pages by title, tags, and body content."""
    _ensure_dirs()
    root = _wiki_root()
    results: List[Dict[str, Any]] = []
    query_lower = query.lower() if query else ""

    for cat_dir in [d for d in root.iterdir() if d.is_dir() and d.name != "__pycache__"]:
        if category and cat_dir.name != category:
            continue
        for md_file in cat_dir.glob("*.md"):
            page = read_page(md_file.stem, category=cat_dir.name)
            if not page:
                continue

            # Filter by tags
            if tags:
                if not set(tags).intersection(set(page.get("tags", []))):
                    continue

            # Filter by query
            if query_lower:
                title_match = query_lower in page["title"].lower()
                body_match = query_lower in page.get("body", "").lower()[:2000]
                tag_match = any(query_lower in t.lower() for t in page.get("tags", []))
                if not (title_match or body_match or tag_match):
                    continue

            results.append({
                "title": page["title"], "category": page["category"],
                "tags": page.get("tags", []), "summary": page.get("summary", "")[:200],
                "related": page.get("related", []), "path": page["path"],
                "contradictions": page.get("contradictions", []),
                "last_updated": page.get("last_updated", ""),
            })

    results.sort(key=lambda r: r["last_updated"], reverse=True)
    return results[:limit]


def traverse_links(start_title: str, depth: int = 2) -> List[Dict[str, Any]]:
    """BFS traverse wiki link graph starting from a page."""
    _ensure_dirs()
    visited: set = set()
    queue: List[Tuple[str, int]] = [(start_title, 0)]
    results: List[Dict[str, Any]] = []

    while queue:
        title, d = queue.pop(0)
        if title in visited or d > depth:
            continue
        visited.add(title)
        page = read_page(title)
        if not page:
            continue
        results.append(page)
        for rel in page.get("related", []):
            if rel not in visited:
                queue.append((rel, d + 1))

    return results


# ── Contradiction detection ────────────────────────────────────

def detect_contradictions() -> List[Dict[str, Any]]:
    """DEPRECATED: use wiki_health_report() for richer output."""
    return wiki_health_report()["issues"]


def wiki_health_report() -> Dict[str, Any]:
    u"""Comprehensive wiki health report with categorized issues and stats.
    
    返回: {
      health_score, total_pages, issues, stats, link_graph
    }
    """
    _ensure_dirs()
    root = _wiki_root()
    all_pages: Dict[str, Dict[str, Any]] = {}
    issues: List[Dict[str, Any]] = []

    # Index all pages
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
    small_pages = 0  # < 200 chars body

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

    # 1. Marked contradictions
    contradiction_count = 0
    for title, page in all_pages.items():
        for con in page.get("contradictions", []):
            if con in all_pages:
                contradiction_count += 1
                issues.append({
                    "check_type": "contradiction",
                    "severity": "high",
                    "page_a": title, "page_b": con,
                    "description": "标注矛盾",
                    "suggestion": f"合并或协调 '{title}' 和 '{con}' 中的矛盾信息",
                })

    # 2. Orphan pages (no incoming links, but links to others)
    all_linked: set = set()
    for page in all_pages.values():
        for rel in page.get("related", []):
            all_linked.add(rel)
    orphan_count = 0
    for title, page in all_pages.items():
        if title not in all_linked and page.get("related", []):
            orphan_count += 1
            issues.append({
                "check_type": "orphan",
                "severity": "medium",
                "page_a": title, "page_b": "",
                "description": f"孤立页面（无入链）",
                "suggestion": f"在相关页面中添加入站链接指向 '{title}'",
            })

    # 3. Dead links (referenced pages that don't exist)
    all_titles = set(all_pages.keys())
    dead_link_count = 0
    for title, page in all_pages.items():
        for rel in page.get("related", []):
            if rel not in all_titles:
                dead_link_count += 1
                issues.append({
                    "check_type": "dead_link",
                    "severity": "high",
                    "page_a": title, "page_b": rel,
                    "description": f"死链（'{rel}' 页面不存在）",
                    "suggestion": f"创建 '{rel}' 页面或删除 '{title}' 中的死链接",
                })

    # 4. Stale pages (last_updated > 30 days ago)
    stale_cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
    stale_count = 0
    for title, page in all_pages.items():
        lu = page.get("last_updated", "")
        if lu and lu < stale_cutoff:
            stale_count += 1
            issues.append({
                "check_type": "stale",
                "severity": "low",
                "page_a": title, "page_b": "",
                "description": f"过期页面（超过30天未更新）",
                "suggestion": "检查信息是否仍然准确，或添加reviewed标记",
            })

    # 5. Thin content
    thin_count = 0
    for title, page in all_pages.items():
        body = page.get("body", "")
        if len(body) < 100:
            thin_count += 1
            issues.append({
                "check_type": "thin_content",
                "severity": "low",
                "page_a": title, "page_b": "",
                "description": f"内容过短（{len(body)} 字符）",
                "suggestion": "丰富页面内容，或考虑与相关页面合并",
            })

    # 6. Missing tags
    no_tags_count = 0
    for title, page in all_pages.items():
        if not page.get("tags"):
            no_tags_count += 1
            issues.append({
                "check_type": "no_tags",
                "severity": "low",
                "page_a": title, "page_b": "",
                "description": "缺少标签",
                "suggestion": "添加相关标签以提高可发现性",
            })

    # 7. Missing summary
    no_summary_count = 0
    for title, page in all_pages.items():
        if not page.get("summary"):
            no_summary_count += 1
            issues.append({
                "check_type": "no_summary",
                "severity": "low",
                "page_a": title, "page_b": "",
                "description": "缺少摘要",
                "suggestion": "添加页面摘要以便快速浏览",
            })

    # Penalty per issue weighted by severity
    penalty = (
        contradiction_count * 5 +
        dead_link_count * 4 +
        orphan_count * 3 +
        stale_count * 1 +
        thin_count * 1 +
        no_tags_count * 1 +
        no_summary_count * 1
    )
    base = max(0, 100 - penalty)
    coverage = (pages_with_body / max(total_pages, 1)) * 10

    # Build link graph adjacency
    link_graph: Dict[str, List[str]] = {}
    for title, page in all_pages.items():
        link_graph[title] = page.get("related", [])

    return {
        "health_score": min(100, int(base + coverage)),
        "total_pages": total_pages,
        "stats": {
            "categories": categories,
            "top_tags": dict(sorted(total_tags.items(), key=lambda x: -x[1])[:15]),
            "total_links": total_related,
            "avg_links_per_page": round(total_related / max(total_pages, 1), 2),
            "pages_with_body": pages_with_body,
            "small_pages": small_pages,
            "orphan_pages": orphan_count,
            "dead_links": dead_link_count,
            "stale_pages": stale_count,
            "thin_pages": thin_count,
            "no_tags": no_tags_count,
            "no_summary": no_summary_count,
            "contradictions": contradiction_count,
        },
        "issues": issues,
        "link_graph": link_graph,
        "checks": [
            {"name": "矛盾检测", "pass": contradiction_count == 0, "count": contradiction_count, "severity": "high"},
            {"name": "死链检测", "pass": dead_link_count == 0, "count": dead_link_count, "severity": "high"},
            {"name": "孤立页面", "pass": orphan_count == 0, "count": orphan_count, "severity": "medium"},
            {"name": "过期内容", "pass": stale_count == 0, "count": stale_count, "severity": "low"},
            {"name": "内容完整度", "pass": thin_count == 0, "count": thin_count, "severity": "low"},
            {"name": "标签覆盖", "pass": no_tags_count == 0, "count": no_tags_count, "severity": "low"},
            {"name": "摘要覆盖", "pass": no_summary_count == 0, "count": no_summary_count, "severity": "low"},
        ],
    }


def list_all_pages() -> List[Dict[str, Any]]:
    """Return summary of all wiki pages for index display."""
    return search_pages(limit=1000)


# ── Graph export (ECharts force-layout) ──────────────────────────

def build_graph(*, category: str = "", keyword: str = "", max_nodes: int = 300) -> Dict[str, Any]:
    u"""Build node/edge graph for ECharts force-layout visualization."""
    _ensure_dirs()
    root = _wiki_root()
    all_pages: Dict[str, Dict[str, Any]] = {}

    for cat_dir in sorted(root.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        for md_file in sorted(cat_dir.glob("*.md")):
            page = read_page(md_file.stem, category=cat_dir.name)
            if page:
                all_pages[page["title"]] = page

    if keyword:
        kw = keyword.lower()
        all_pages = {t: p for t, p in all_pages.items()
                     if kw in t.lower() or any(kw in tag.lower() for tag in p.get("tags", []))}
    if category:
        all_pages = {t: p for t, p in all_pages.items() if p.get("category", "") == category}

    in_degree: Dict[str, int] = {t: 0 for t in all_pages}
    for p in all_pages.values():
        for rel in p.get("related", []):
            if rel in in_degree:
                in_degree[rel] += 1

    cat_colors = {"entities": "#4d9fff", "topics": "#a855f7", "contradictions": "#ef4444"}
    titles = list(all_pages.keys())
    if max_nodes > 0 and len(titles) > max_nodes:
        titles.sort(key=lambda t: len(all_pages[t].get("related", [])) + in_degree.get(t, 0), reverse=True)
        titles = titles[:max_nodes]
        keep = set(titles)
        all_pages = {t: p for t, p in all_pages.items() if t in keep}

    cat_counts: Dict[str, int] = {}
    total_links = 0
    nodes = []
    for title in titles:
        p = all_pages[title]
        link_count = len(p.get("related", [])) + in_degree.get(title, 0)
        total_links += link_count
        cat_name = p.get("category", "entities")
        cat_counts[cat_name] = cat_counts.get(cat_name, 0) + 1
        symbol_size = min(12 + link_count * 3, 55)
        has_issues = bool(p.get("contradictions") or p.get("issues"))
        nodes.append({
            "id": title,
            "name": title if len(title) <= 50 else title[:47] + "...",
            "category": cat_name,
            "symbolSize": symbol_size,
            "tags": p.get("tags", [])[:5],
            "summary": p.get("summary", ""),
            "linkCount": link_count,
            "hasIssues": has_issues,
            "itemStyle": {"color": "#ef4444" if has_issues else cat_colors.get(cat_name, "#4d9fff")},
        })

    id_set = set(titles)
    edges = [{"source": t, "target": r} for t in titles for r in all_pages[t].get("related", []) if r in id_set]

    return {
        "nodes": nodes, "edges": edges,
        "stats": {"totalNodes": len(nodes), "totalEdges": len(edges),
                  "avgLinksPerPage": round(total_links / max(len(nodes), 1), 2),
                  "categories": cat_counts},
    }


# ── Cross-linking via embedding similarity ──────────────────────

def auto_link_page(title: str, body: str, all_titles: List[str],
                   threshold: float = None) -> List[str]:
    u"""自动语义关联：嵌入相似度 → top-5 相关页面。

    模型路径：embed_texts_semantic → InfraEmbeddingAdapter → infra ModelManager。
    阈值可通过 AIPLAT_WIKI_LINK_THRESHOLD 环境变量配置。
    """
    if threshold is None:
        threshold = float(os.getenv("AIPLAT_WIKI_LINK_THRESHOLD", "0.35"))
    existing = [t for t in all_titles if t != title]
    if not existing:
        return []

    from core.harness.knowledge.embedder import embed_text_semantic, embed_texts_semantic, cosine_similarity

    target_vec = embed_text_semantic(body[:2000])
    if target_vec is None:
        return []

    others = [read_page(t) for t in existing if read_page(t)]
    texts = [(p["body"] or "")[:2000] for p in others]
    other_vecs = embed_texts_semantic(texts)

    scored = []
    for t, v in zip(existing, other_vecs):
        if v is not None:
            sim = cosine_similarity(target_vec, v)
            if sim > threshold:
                scored.append((t, sim))
    scored.sort(key=lambda x: -x[1])
    return [s[0] for s in scored[:5]]


# ── LLM-powered curation ────────────────────────────────────────

async def llm_curate_page(title: str, body: str, *, existing_titles: List[str] = None,
                           source_doc_id: str = "") -> Dict[str, Any]:
    """Use LLM to read a new wiki page, extract entities, detect contradictions,
    update related pages, and generate a proper summary.

    Returns: { title, category, summary, tags, related, entities_found, contradictions, merge_candidates }
    """
    existing_titles = existing_titles or []
    result: Dict[str, Any] = {
        "title": title, "category": "entities", "summary": body[:300].replace("\n", " "),
        "tags": [], "related": [], "entities_found": [], "contradictions": [], "merge_candidates": [],
    }

    # Build prompt for LLM
    existing_list = "\n".join(f"- {t}" for t in existing_titles[:50]) if existing_titles else "(none)"
    prompt = f"""You are a knowledge curator. Read the following new wiki page and analyze it.

=== NEW PAGE ===
Title: {title}
Content (first 5000 chars):
{body[:5000]}

=== EXISTING WIKI PAGES ===
{existing_list}

=== TASKS ===
1. Generate a 2-3 sentence summary (Chinese preferred, max 300 chars)
2. Suggest the best category: entities, topics, or contradictions
3. Extract 3-8 tags (keywords, lowercase)
4. Identify 2-5 existing pages that this new page is related to (from the list above — choose titles that closely match on topic/concept)
5. If the content discusses conflicting information between two entities, list the contradiction pair
6. If this page is nearly identical to an existing page (same topic, same content), suggest it as a merge candidate

=== OUTPUT FORMAT ===
Reply with ONLY a JSON object (no markdown fences, no explanation):
{{"summary":"...","category":"entities","tags":["tag1","tag2"],"related":["Existing Page Title"],"entities_found":["Entity1","Entity2"],"contradictions":[{{"a":"PageA","b":"PageB","detail":"why"}}],"merge_candidates":[{{"target":"PageTitle","reason":"duplicate content"}}]}}
"""
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = best_model_for_purpose("wiki_curation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": "You are a knowledge curation assistant. Reply with JSON only, no markdown fences."},
            {"role": "user", "content": prompt},
        ]
        resp = await model.generate(messages, config=None)
        content = resp.content if hasattr(resp, 'content') else str(resp)
        # Parse JSON from response — try multiple extraction strategies
        if content.startswith("```"):
            # Strip markdown code fences
            content = content.strip("`").strip()
            if content.startswith("json"):
                content = content[4:].strip()
        # Find the outermost JSON object
        json_match = re.search(r'\{[\s\S]*?\}', content)
        if json_match:
            data = _json.loads(json_match.group(0))
            result["summary"] = str(data.get("summary", result["summary"]))[:500]
            result["category"] = str(data.get("category", "entities"))
            result["tags"] = list(data.get("tags", []))[:8]
            result["related"] = [t for t in (data.get("related", []) or []) if t in existing_titles][:10]
            result["entities_found"] = list(data.get("entities_found", []))[:10]
            result["contradictions"] = list(data.get("contradictions", []))[:5]
            result["merge_candidates"] = list(data.get("merge_candidates", []))[:3]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"llm_curate_page failed for '{title}': {e}")
        import traceback
        result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        result["fallback"] = True

    return result


__all__ = [
    "read_page", "write_page", "search_pages", "traverse_links",
    "detect_contradictions", "list_all_pages", "llm_curate_page", "_wiki_root",
]
