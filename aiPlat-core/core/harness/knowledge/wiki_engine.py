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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Configuration ──────────────────────────────────────────────

FRONTMATTER_FIELDS = {
    "title": "", "category": "entities", "tags": [], "related": [],
    "contradictions": [], "source_articles": [], "last_updated": "",
    "summary": "", "version": "1", "stale_references": [],
}

def _wiki_root() -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    return Path(home) / "wiki"


def parse_title_from_uri(source_uri: str) -> str:
    u"""Extract a readable title from an upload filename.

    Examples:
      'req_01KS_1080p_xtdowner.com_放弃RAG吧_LLM知识库新范式_Karpathy新思路.mp4'
        → '放弃 RAG：LLM 知识库新范式'
    """
    fname = Path(source_uri).stem
    for prefix in ["preview_", "req_", "src_"]:
        if fname.startswith(prefix):
            fname = fname[len(prefix):]
    fname = re.sub(r'^[A-Z0-9]{26,30}_', '', fname)   # strip ULID
    fname = re.sub(r'\d{3,4}p_', '', fname)            # strip resolution
    fname = re.sub(r'xtdowner\.com_', '', fname)        # strip domain
    fname = re.sub(r'(_ai_|_技术_|_分享_)', ' · ', fname)
    fname = re.sub(r'(?<=[\u4e00-\u9fff])_(?=[\u4e00-\u9fff])', ' ', fname)
    for sfx in ['.edited', '.preview_cache', '.mp4', '.avi', '.mkv', '.json']:
        fname = fname.replace(sfx, '')
    fname = fname.replace('_', ' ').strip()
    fname = re.sub(r'\s{2,}', ' ', fname)
    parts = [p.strip() for p in re.split(r'[ ·,|：:\-]+', fname) if len(p.strip()) >= 2]
    if parts:
        return parts[0][:60]
    return fname[:60]

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
               source_articles: List[str] = None, stale_references: List[str] = None,
               version: str = "1", summary: str = "") -> str:
    """Create or update a wiki page. Returns the file path."""
    _ensure_dirs()
    root = _wiki_root()
    name = re.sub(r"[<>:\"/\\|?*]", "_", title)[:120]
    existing = read_page(title, category=category)
    now = datetime.now(timezone.utc).isoformat()

    # Merge with existing if updating
    if existing:
        tags = list(set((existing.get("tags") or []) + (tags or [])))
        related = related if related is not None else list(set(
            (existing.get("related") or [])))      # replace, not merge (enable dead link cleanup)
        contradictions = list(set((existing.get("contradictions") or []) + (contradictions or [])))
        source_articles = list(set((existing.get("source_articles") or []) + (source_articles or [])))
        stale_references = stale_references if stale_references is not None else (existing.get("stale_references") or [])
        version = version or existing.get("version", "1")
        summary = summary or existing.get("summary", "")

    fm_lines = [
        f"title: {title}",
        f"category: {category}",
        f"tags: [{', '.join(tags or [])}]",
        f"related: [{', '.join(related or [])}]",
        f"contradictions: [{', '.join(contradictions or [])}]",
        f"source_articles: [{', '.join(source_articles or [])}]",
        f"stale_references: [{', '.join(stale_references or [])}]",
        f"last_updated: {now}",
        f"version: {version or '1'}",
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
                             "last_updated": datetime.now(timezone.utc).isoformat()}
    idx["last_updated"] = datetime.now(timezone.utc).isoformat()
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
            value = kwargs[key]
            # Filter dead links from related
            if key == "related" and isinstance(value, list):
                all_titles = set(p["title"] for p in search_pages(limit=1000))
                value = [r for r in value if r in all_titles or r == title]
            existing[key] = value

    name = kwargs.get("new_title", kwargs.get("title", title))
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


def delete_page(title: str) -> bool:
    u"""Delete a wiki page by title, removing from disk and index."""
    found = None
    cat_name = ""
    for cat_dir in _wiki_root().iterdir():
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        md_path = cat_dir / f"{title}.md"
        if md_path.exists():
            found = md_path
            cat_name = cat_dir.name
            break
    if not found:
        return False

    found.unlink()
    idx_path = _wiki_root() / "index.json"
    if idx_path.exists():
        try:
            idx = _json.loads(idx_path.read_text(encoding="utf-8"))
            idx.get("pages", {}).pop(title, None)
            idx_path.write_text(_json.dumps(idx, indent=2, ensure_ascii=False))
        except Exception:
            pass
    return True


def delete_all_pages() -> Dict[str, Any]:
    u"""Delete ALL wiki pages, reset index, and clear KB document wiki_pages references."""
    _ensure_dirs()
    root = _wiki_root()
    deleted = 0

    for cat_dir in root.iterdir():
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        for md_file in cat_dir.glob("*.md"):
            md_file.unlink()
            deleted += 1

    idx_path = root / "index.json"
    idx_path.write_text(_json.dumps({"pages": {}, "last_updated": ""}, indent=2, ensure_ascii=False))

    # Clear wiki_pages from KB document meta
    try:
        import sqlite3 as _sq
        kb_dir = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
        kb_db = os.path.join(kb_dir, "default", "kb.sqlite3")
        if os.path.exists(kb_db):
            conn = _sq.connect(kb_db)
            conn.row_factory = _sq.Row
            docs = conn.execute("SELECT doc_id, meta_json FROM documents WHERE tenant_id='default'").fetchall()
            for d in docs:
                try:
                    meta = _json.loads(d["meta_json"] or "{}")
                    if "wiki_pages" in meta:
                        del meta["wiki_pages"]
                        conn.execute("UPDATE documents SET meta_json=? WHERE doc_id=? AND tenant_id='default'",
                                     (_json.dumps(meta, ensure_ascii=False), d["doc_id"]))
                        conn.commit()
                except Exception:
                    pass
            conn.close()
    except Exception:
        pass

    return {"deleted": deleted}


# ── Knowledge proposals (merge/update/supplement/contradict) ──────

def _proposals_path() -> Path:
    return _wiki_root() / "proposals.json"


def load_proposals() -> List[Dict[str, Any]]:
    u"""Load all proposals from disk."""
    pp = _proposals_path()
    if not pp.exists():
        return []
    try:
        data = _json.loads(pp.read_text(encoding="utf-8"))
        return data.get("proposals", [])
    except Exception:
        return []


def save_proposal(proposal: Dict[str, Any]) -> str:
    u"""Add or update a proposal. Returns the proposal id."""
    pp = _proposals_path()
    _ensure_dirs()
    proposals = load_proposals()
    pid = proposal.get("id") or f"prop_{int(time.time() * 1000):x}"
    proposal["id"] = pid
    # Update existing or append
    for i, p in enumerate(proposals):
        if p.get("id") == pid:
            proposals[i] = proposal
            break
    else:
        proposals.append(proposal)
    pp.write_text(_json.dumps({"proposals": proposals, "last_updated": datetime.now(timezone.utc).isoformat()},
                              indent=2, ensure_ascii=False))
    return pid


def update_proposal_status(proposal_id: str, status: str) -> bool:
    u"""Update a proposal's status (pending→approved→rejected)."""
    proposals = load_proposals()
    for p in proposals:
        if p.get("id") == proposal_id:
            p["status"] = status
            p["resolved_at"] = datetime.now(timezone.utc).isoformat()
            pp = _proposals_path()
            pp.write_text(_json.dumps({"proposals": proposals, "last_updated": datetime.now(timezone.utc).isoformat()},
                                      indent=2, ensure_ascii=False))
            return True
    return False


def apply_proposal(proposal_id: str) -> Dict[str, Any]:
    u"""Execute an approved proposal: merge, update, supplement, or contrad.

    Returns: {success: bool, message: str, action: str}
    """
    proposals = load_proposals()
    prop = next((p for p in proposals if p.get("id") == proposal_id), None)
    if not prop:
        return {"success": False, "message": "proposal not found", "action": ""}
    if prop.get("status") != "approved":
        return {"success": False, "message": "proposal not yet approved", "action": ""}

    action = prop.get("action", "")
    from_title = prop.get("from_title", "")
    to_title = prop.get("to_title", "")

    if action == "merge":
        return _execute_merge(prop, from_title, to_title)
    elif action == "update":
        return _execute_update(prop, from_title, to_title)
    elif action == "supplement":
        return _execute_supplement(prop, from_title, to_title)
    elif action == "contradict":
        return _execute_contradict(prop, from_title, to_title)
    return {"success": False, "message": f"unknown action: {action}", "action": action}


def _execute_merge(prop, from_title, to_title) -> Dict[str, Any]:
    u"""Merge two pages: combine bodies, update links, delete merged page."""
    from_page = read_page(from_title)
    to_page = read_page(to_title)
    if not from_page or not to_page:
        return {"success": False, "message": "one or both pages not found", "action": "merge"}

    merged_body = (to_page.get("body") or "") + "\n\n---\n\n合并自 [[{from_title}]]:\n\n".format(from_title=from_title) + (from_page.get("body") or "")
    merged_tags = list(set((to_page.get("tags") or []) + (from_page.get("tags") or [])))
    merged_related = list(set((to_page.get("related") or []) + (from_page.get("related") or []) + [from_title]))
    merged_related = [r for r in merged_related if r != to_title]  # remove self-ref
    merged_sources = list(set((to_page.get("source_articles") or []) + (from_page.get("source_articles") or [])))

    write_page(to_title, merged_body[:50000],
               category=to_page.get("category", "entities"),
               tags=merged_tags[:10],
               related=merged_related[:15],
               summary=to_page.get("summary", "") or from_page.get("summary", ""),
               source_articles=merged_sources)
    # Redirect references from from_title to to_title in all pages
    all_pages = search_pages(limit=1000)
    updated = 0
    for p in all_pages:
        if from_title in (p.get("related") or []):
            new_related = [to_title if r == from_title else r for r in p["related"]]
            update_page(p["title"], related=new_related)
            updated += 1
    delete_page(from_title)
    update_proposal_status(prop["id"], "resolved")
    return {"success": True, "message": f"merged '{from_title}' into '{to_title}', updated {updated} references", "action": "merge"}


def _execute_update(prop, from_title, to_title) -> Dict[str, Any]:
    u"""Update existing page with new content from another page."""
    to_page = read_page(to_title)
    if not to_page:
        return {"success": False, "message": "target page not found", "action": "update"}
    from_page = read_page(from_title)
    new_body = (from_page.get("body") or "") if from_page else (to_page.get("body") or "")
    version = int(to_page.get("version", 1)) + 1
    update_page(to_title, body=new_body, version=str(version))
    # Mark stale references
    all_pages = search_pages(limit=1000)
    for p in all_pages:
        if to_title in (p.get("related") or []):
            stale = list(set((p.get("stale_references") or []) + [to_title]))
            update_page(p["title"], stale_references=stale[:10])
    update_proposal_status(prop["id"], "resolved")
    return {"success": True, "message": f"updated '{to_title}' to v{version}, marked stale references", "action": "update"}


def _execute_supplement(prop, from_title, to_title) -> Dict[str, Any]:
    u"""Append new content to existing page body."""
    to_page = read_page(to_title)
    from_page = read_page(from_title)
    if not to_page:
        return {"success": False, "message": "target page not found", "action": "supplement"}
    appendix = (from_page.get("body") or "") if from_page else ""
    if appendix:
        new_body = (to_page.get("body") or "") + "\n\n---\n\n补充内容 (来源: {from_title}):\n\n".format(from_title=from_title) + appendix
        update_page(to_title, body=new_body[:50000])
    update_proposal_status(prop["id"], "resolved")
    return {"success": True, "message": f"supplemented '{to_title}'", "action": "supplement"}


def _execute_contradict(prop, from_title, to_title) -> Dict[str, Any]:
    u"""Mark contradiction between two pages."""
    for t in [from_title, to_title]:
        page = read_page(t)
        if page:
            other = to_title if t == from_title else from_title
            contras = list(set((page.get("contradictions") or []) + [other]))
            update_page(t, contradictions=contras[:10])
    update_proposal_status(prop["id"], "resolved")
    return {"success": True, "message": f"marked contradiction between '{from_title}' and '{to_title}'", "action": "contradict"}


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
                "source_articles": page.get("source_articles", []),
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
    """Comprehensive wiki health report — delegates to extensible WikiHealthRegistry.
    
    To add a new health check: add a WikiRule subclass in wiki_health_rules.py.
    """
    from core.harness.knowledge.wiki_health_rules import get_wiki_registry
    return get_wiki_registry().run().to_dict()


def list_all_pages() -> List[Dict[str, Any]]:
    """Return summary of all wiki pages for index display."""
    return search_pages(limit=1000)


# ── Graph export (ECharts force-layout) ──────────────────────────

def build_graph(*, category: str = "", keyword: str = "", source: str = "", max_nodes: int = 300) -> Dict[str, Any]:
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

    if source:
        all_pages = {t: p for t, p in all_pages.items()
                     if any(s.startswith(source + ":") for s in (p.get("source_articles") or []))}

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
        "tags": [], "related": [], "entities_found": [], "contradictions": [],
        "merge_candidates": [], "knowledge_atoms": [],
    }

    # Build prompt for LLM — knowledge atom extraction
    existing_list = "\n".join(f"- {t}" for t in existing_titles[:80]) if existing_titles else "(none)"
    from core.harness.utils.prompt_loader import _async_prompt_resolve
    prompt_content = f"""=== CONTENT (first 8000 chars) ===
Title: {title}
{body[:8000]}

=== EXISTING WIKI PAGES ===
{existing_list}

=== TASKS ===
1. Generate a 2-3 sentence Chinese summary of the key insight (max 300 chars)

2. If this content covers multiple distinct concepts/methods/facts, extract them as knowledge_atoms:
   Each knowledge_atom = a self-contained piece of knowledge that could stand alone as a wiki page.
   For each atom: provide {{
     "title": "a short readable title (Chinese preferred, 5-15 chars)",
     "body": "the knowledge content (2-8 sentences, self-contained, Chinese preferred)",
     "category": "entities" | "topics",
     "tags": ["keyword1", "keyword2"]
   }}
   Aim to extract 2-6 atoms if the content is long/complex. Each atom should be a coherent knowledge unit.

3. Suggest the best overall category: entities or topics

4. Extract 3-8 tags (lowercase keywords)

5. Identify 2-8 existing wiki pages that this content relates to (from the list above)

6. If the content discusses conflicting/competing viewpoints between entities, list contradictions

7. If this content overlaps heavily with any existing page (same topic, same claims), suggest it as a merge candidate

=== OUTPUT FORMAT ===
Reply with ONLY a JSON object (no markdown fences, no explanation):
{{"title":"优化的可读标题","summary":"...","category":"entities","tags":["tag1","tag2"],"related":["Existing Page"],"entities_found":["概念1","概念2"],"knowledge_atoms":[{{"title":"原子标题","body":"知识片段正文","category":"entities","tags":["tag"]}}],"contradictions":[{{"a":"PageA","b":"PageB","detail":"why"}}],"merge_candidates":[{{"target":"PageTitle","reason":"duplicate"}}]}}
"""

    prompt = await _async_prompt_resolve("wiki-curator", content=prompt_content)
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = best_model_for_purpose("wiki_curation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("wiki-system-role")},
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
        # Find the outermost JSON object (greedy match to handle nested JSON)
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                data = _json.loads(json_match.group(0))
            except _json.JSONDecodeError:
                # Try cleaning: remove trailing comma before closing brace
                cleaned = re.sub(r',\s*}', '}', json_match.group(0))
                try:
                    data = _json.loads(cleaned)
                except _json.JSONDecodeError:
                    data = {}  # LLM response was malformed JSON
            if data:
                result["title"] = str(data.get("title", result["title"]))[:120]
                result["summary"] = str(data.get("summary", result["summary"]))[:500]
                result["category"] = str(data.get("category", "entities"))
                result["tags"] = list(data.get("tags", []))[:8]
                result["related"] = [t for t in (data.get("related", []) or []) if t in existing_titles][:10]
                result["entities_found"] = list(data.get("entities_found", []))[:10]
                result["contradictions"] = list(data.get("contradictions", []))[:5]
                result["merge_candidates"] = list(data.get("merge_candidates", []))[:3]
                result["knowledge_atoms"] = list(data.get("knowledge_atoms", []))[:6]
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
