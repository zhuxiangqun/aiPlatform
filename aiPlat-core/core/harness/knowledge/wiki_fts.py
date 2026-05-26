"""
Wiki FTS5 Index — full-text keyword search for wiki page titles, tags, summaries.

Stores an FTS5 index at ~/.aiplat/wiki/fts.db for fast keyword matching.
Complements embedding-based semantic search (embedder.py) with exact name lookups.
"""

from __future__ import annotations

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
            title, tags, summary, body_preview, content='', tokenize='unicode61'
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


def fts_search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    u"""Keyword search wiki pages via FTS5. Returns [{title, snippet}].

    Use for exact name matches (e.g. 'OpenViking'→finds OpenViking page)
    where embedding search may miss due to vocabulary gap.
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
        return results
    except Exception:
        return []
    finally:
        conn.close()


def fts_rebuild_on_update() -> None:
    u"""Rebuild FTS index if wiki pages have changed. Call after import/curate."""
    fts_index_pages()
