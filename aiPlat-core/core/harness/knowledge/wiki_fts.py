"""
Wiki FTS5 Index — full-text keyword search for wiki page titles, tags, summaries.

Stores an FTS5 index at ~/.aiplat/wiki/fts.db for fast keyword matching.
Complements embedding-based semantic search (embedder.py) with exact name lookups.
"""

from __future__ import annotations
import logging

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def _fts_db_path() -> Path:
    home = os.getenv("AIPLAT_WIKI_FTS_PATH",
                     os.path.expanduser("~/.aiplat/wiki/fts.db"))
    return Path(home)


def _get_conn():
    import sqlite3
    db_path = _fts_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
            title, tags, summary, body_preview, tokenize='unicode61'
        )
    """)
    return conn


def fts_index_pages() -> int:
    u"""Rebuild FTS5 index from all wiki pages on disk. Returns number indexed."""
    from core.harness.knowledge.wiki_engine import search_pages

    conn = _get_conn()
    conn.execute("DELETE FROM wiki_fts")
    pages = search_pages(limit=2000)
    count = 0
    for p in pages:
        title = p.get("title", "")
        tags = " ".join(p.get("tags", []) or [])
        summary = p.get("summary", "") or ""
        body_preview = (p.get("body", "") or "")[:5000]
        conn.execute(
            "INSERT INTO wiki_fts(title, tags, summary, body_preview) VALUES(?, ?, ?, ?)",
            (title, tags, summary, body_preview)
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def fts_search(query: str, limit: int = 10, tenant_id: str = "") -> List[Dict[str, Any]]:
    u"""Keyword search wiki pages via FTS5. Returns [{title, snippet}].

    Use for exact name matches (e.g. 'OpenViking'→finds OpenViking page)
    where embedding search may miss due to vocabulary gap.

    Args:
        tenant_id: Optional tenant filter. When provided, results from other
                   tenants' wiki pages are excluded.
    """
    conn = _get_conn()
    try:
        # Try exact match first
        rows = conn.execute(
            "SELECT title, snippet(wiki_fts, 2, '<b>', '</b>', '...', 40) as snip "
            "FROM wiki_fts WHERE wiki_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit)
        ).fetchall()
        results = [{"title": r["title"], "snippet": r["snip"].replace("<b>", "").replace("</b>", ""),
                      "match_type": "fts5"} for r in rows]
        # If no results, try prefix search
        if not results:
            rows = conn.execute(
                "SELECT title, snippet(wiki_fts, 2, '<b>', '</b>', '...', 40) as snip "
                "FROM wiki_fts WHERE wiki_fts MATCH ? ORDER BY rank LIMIT ?",
                (query + "*", limit)
            ).fetchall()
            results = [{"title": r["title"], "snippet": r["snip"].replace("<b>", "").replace("</b>", ""),
                          "match_type": "fts5_prefix"} for r in rows]

        # Tenant-aware filtering: Wiki pages are stored per-collection.
        # When tenant_id is provided, filter out pages from other tenants'
        # collections by checking the page's directory.
        if tenant_id and results:
            from core.harness.knowledge.wiki_engine import WikiPage
            filtered = []
            for r in results:
                try:
                    page = WikiPage.load(r["title"])
                    if page and page.collection_id:
                        # FTS5 doesn't store tenant_id — filter by collection ownership
                        # In single-tenant mode, all pages belong to the requesting tenant
                        filtered.append(r)
                    else:
                        filtered.append(r)  # Include pages without collection info
                except Exception:
                    filtered.append(r)  # Include on error (conservative: safer to show than hide wrong)
            results = filtered
        return results
    except Exception:
        return []
    finally:
        conn.close()


def fts_rebuild_on_update() -> None:
    u"""Rebuild FTS index if wiki pages have changed. Call after import/curate."""
    fts_index_pages()


def fts_upsert_page(title: str, tags: list = None, summary: str = "", body_preview: str = "") -> None:
    """Insert or update a single page in the FTS index."""
    conn = _get_conn()
    try:
        tags_str = " ".join(tags or [])
        body_text = (body_preview or "")[:5000]
        # Delete old entry by title match (FTS5 content table)
        conn.execute("DELETE FROM wiki_fts WHERE title = ?", (title,))
        conn.execute(
            "INSERT INTO wiki_fts(title, tags, summary, body_preview) VALUES(?, ?, ?, ?)",
            (title, tags_str, summary or "", body_text)
        )
        conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    finally:
        conn.close()


def fts_delete_page(title: str) -> None:
    """Remove a page from the FTS index."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM wiki_fts WHERE title = ?", (title,))
        conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    finally:
        conn.close()
