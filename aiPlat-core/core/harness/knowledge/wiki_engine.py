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
from datetime import datetime
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
    """Find pages that have marked contradictions. Returns list with conflict details."""
    _ensure_dirs()
    root = _wiki_root()
    conflicts: List[Dict[str, Any]] = []
    all_pages: Dict[str, Dict[str, Any]] = {}

    # Index all pages
    for cat_dir in root.iterdir():
        if not cat_dir.is_dir() or cat_dir.name == "contradictions":
            continue
        for md_file in cat_dir.glob("*.md"):
            page = read_page(md_file.stem, category=cat_dir.name)
            if page:
                all_pages[page["title"]] = page

    # Check for contradictions
    for title, page in all_pages.items():
        for con in page.get("contradictions", []):
            if con in all_pages:
                conflicts.append({
                    "page_a": title, "page_b": con,
                    "severity": "unknown",
                    "description": f"Marked contradiction between '{title}' and '{con}'",
                })

    # Find orphan pages (no incoming links)
    all_linked: set = set()
    for page in all_pages.values():
        for rel in page.get("related", []):
            all_linked.add(rel)
    for title, page in all_pages.items():
        if title not in all_linked and page.get("related", []):
            conflicts.append({
                "page_a": title, "page_b": "",
                "severity": "orphan",
                "description": f"Page '{title}' links to others but has no incoming links",
            })

    return conflicts


def list_all_pages() -> List[Dict[str, Any]]:
    """Return summary of all wiki pages for index display."""
    return search_pages(limit=1000)


__all__ = [
    "read_page", "write_page", "search_pages", "traverse_links",
    "detect_contradictions", "list_all_pages", "_wiki_root",
]
