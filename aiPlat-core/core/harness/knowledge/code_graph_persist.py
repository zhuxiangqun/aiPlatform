"""
Code Graph SQLite Persistence — survives process restart.

Schema:
  files     — tracked source files (path, mtime, hash, layer)
  symbols   — extracted symbols (name, kind, file_id, line)
  edges     — import/call relationships (from_sym, to_sym, kind)
  FTS5      — full-text index on files.path and symbols.name

Replaces the in-memory _CACHE dict in code_graph.py with persistent storage.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    mtime REAL NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    layer TEXT NOT NULL DEFAULT '',
    ext TEXT NOT NULL DEFAULT '',
    issue_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_file TEXT NOT NULL,
    to_file TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'import',
    label TEXT NOT NULL DEFAULT '',
    line INTEGER NOT NULL DEFAULT 0,
    cross INTEGER NOT NULL DEFAULT 0,
    UNIQUE(from_file, to_file, kind, label, line)
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_file);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_file);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- FTS5 full-text index for search
CREATE VIRTUAL TABLE IF NOT EXISTS fts_files USING fts5(path, content='files', content_rowid='id');
"""

_DB_PATH: Optional[str] = None


def _db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
        _DB_PATH = os.path.join(home, "code_graph.db")
    return _DB_PATH


def init_db():
    """Initialize SQLite database with schema."""
    import sqlite3
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.executescript(_SCHEMA)
    # Migration: add label/line/cross columns if upgrading from old schema
    for col, typ in (("label", "TEXT NOT NULL DEFAULT ''"),
                     ("line", "INTEGER NOT NULL DEFAULT 0"),
                     ("cross", "INTEGER NOT NULL DEFAULT 0")):
        try:
            conn.execute(f"ALTER TABLE edges ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # column already exists
    # Migration: add parent column to symbols table
    try:
        conn.execute("ALTER TABLE symbols ADD COLUMN parent TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def _get_conn():
    import sqlite3
    return sqlite3.connect(_db_path(), timeout=5.0)


def get_cache_info() -> Dict[str, Any]:
    """Return cache metadata (age, freshness)."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='last_build'").fetchone()
        last_build = float(row[0]) if row else 0
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        return {"last_build": last_build, "files_indexed": count,
                "age_seconds": time.time() - last_build if last_build else 0}
    finally:
        conn.close()


def has_cache() -> bool:
    """Check if cache exists and has data."""
    if not os.path.exists(_db_path()):
        return False
    conn = _get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        return count > 0
    finally:
        conn.close()


def get_cached_repo_root() -> Optional[str]:
    """Return the repo_root stored when the cache was last saved, or None if not set."""
    if not os.path.exists(_db_path()):
        return None
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='repo_root'").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def clear_all_cache():
    """Wipe all graph data from SQLite — forces full rebuild on next call."""
    if not os.path.exists(_db_path()):
        return
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM symbols")
        conn.execute("DELETE FROM meta")
        conn.execute("DELETE FROM fts_files")
        conn.commit()
    finally:
        conn.close()


def load_nodes() -> Dict[str, Dict[str, Any]]:
    """Load all file nodes with adjacency and mtime from SQLite."""
    conn = _get_conn()
    try:
        nodes: Dict[str, Dict[str, Any]] = {}
        rows = conn.execute("SELECT path, layer, ext, issue_count, mtime, content_hash FROM files").fetchall()
        for path, layer, ext, issues, mtime, chash in rows:
            nodes[path] = {"id": path, "path": path, "ext": ext,
                           "layer": layer, "out": [], "in": 0, "issue_count": issues,
                           "_mtime": mtime, "_hash": chash, "symbols": []}
        # Load symbols
        sym_rows = conn.execute("SELECT file_path, name, kind, line, parent FROM symbols").fetchall()
        for filepath, name, kind, line, parent in sym_rows:
            if filepath in nodes:
                nodes[filepath]["symbols"].append([name, kind, line, parent])
        # Populate adjacency
        edge_rows = conn.execute("SELECT from_file, to_file FROM edges WHERE kind='import'").fetchall()
        for src, dst in edge_rows:
            if src in nodes and dst in nodes and src != dst:
                nodes[src]["out"].append(dst)
                nodes[dst]["in"] += 1
        return nodes
    finally:
        conn.close()


def load_edges() -> List[Dict[str, str]]:
    """Load all edges with full metadata (kind, label, line, cross)."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT from_file, to_file, kind, label, line, cross FROM edges").fetchall()
        result = []
        for r in rows:
            e = {"from": r[0], "to": r[1], "kind": r[2]}
            if r[3]:
                e["label"] = r[3]
            if r[4]:
                e["line"] = r[4]
            if r[5]:
                e["cross"] = True
            result.append(e)
        return result
    finally:
        conn.close()


def save_graph(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]], repo_root: Path = None):
    """Persist the full graph to SQLite (replace existing). Stores mtime for incremental sync."""
    import sqlite3
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM symbols")
        conn.execute("DELETE FROM fts_files")

        now = time.time()
        for filepath, node in nodes.items():
            full = repo_root / filepath if repo_root else Path(filepath)
            mtime = full.stat().st_mtime if full.exists() else 0
            content_hash = _content_hash(full) if full.exists() else ""
            conn.execute(
                "INSERT OR REPLACE INTO files (path, mtime, content_hash, layer, ext, issue_count) VALUES (?,?,?,?,?,?)",
                (filepath, mtime, content_hash, _detect_layer(filepath), node.get("ext", ""), node.get("issue_count", 0))
            )
        # Save symbols per file
        for filepath, node in nodes.items():
            for sym in node.get("symbols", []):
                if not isinstance(sym, (list, tuple)):
                    continue
                name = sym[0] if len(sym) > 0 else ""
                kind = sym[1] if len(sym) > 1 else ""
                line = sym[2] if len(sym) > 2 else 0
                parent = sym[3] if len(sym) > 3 else None
                conn.execute(
                    "INSERT INTO symbols (file_path, name, kind, line, parent) VALUES (?,?,?,?,?)",
                    (filepath, name, kind, line, parent)
                )
        for e in edges:
            conn.execute(
                "INSERT OR REPLACE INTO edges (from_file, to_file, kind, label, line, cross) VALUES (?,?,?,?,?,?)",
                (e["from"], e["to"], e.get("kind", "import"),
                 e.get("label", ""), e.get("line", 0),
                 1 if e.get("cross") else 0)
            )
        # FTS sync
        conn.execute("INSERT INTO fts_files(fts_files) VALUES('rebuild')")
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_build', ?)", (str(now),))
        if repo_root:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('repo_root', ?)",
                (str(repo_root.resolve()),)
            )
        conn.commit()
    finally:
        conn.close()


def search_fts(query: str, limit: int = 20) -> List[str]:
    """Full-text search file paths and symbol names."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT path FROM fts_files WHERE fts_files MATCH ? LIMIT ?",
            (query, limit)
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def cross_edges_cached() -> bool:
    """Check if cross-call edges and frontend-backend links have been computed."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='cross_edges_computed'").fetchone()
        return row is not None and row[0] == "1"
    finally:
        conn.close()


def set_cross_edges_cached():
    """Mark that cross-call edges and frontend-backend links have been computed."""
    conn = _get_conn()
    try:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('cross_edges_computed', '1')")
        conn.commit()
    finally:
        conn.close()


def clear_cross_edges_cache():
    """Invalidate cross-call edges cache (e.g., after file changes)."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM edges WHERE kind IN ('calls', 'cross_call')")
        conn.execute("DELETE FROM meta WHERE key='cross_edges_computed'")
        conn.commit()
    finally:
        conn.close()


def save_cross_edges(edges: List[Dict[str, str]]):
    """Persist computed cross-call/cross-language edges to SQLite."""
    import sqlite3
    conn = sqlite3.connect(_db_path(), timeout=5.0)
    try:
        # Remove old cross edges before inserting new ones
        conn.execute("DELETE FROM edges WHERE kind IN ('calls', 'cross_call')")
        for e in edges:
            if e.get("kind") in ("calls", "cross_call"):
                conn.execute(
                    "INSERT OR REPLACE INTO edges (from_file, to_file, kind, label, line, cross) VALUES (?,?,?,?,?,?)",
                    (e["from"], e["to"], e.get("kind", "calls"),
                     e.get("label", ""), e.get("line", 0),
                     1 if e.get("cross") else 0)
                )
        conn.commit()
    finally:
        conn.close()


def _detect_layer(path: str) -> str:
    """Detect architecture layer from file path (sync'd with code_graph._layer_bucket)."""
    if path.startswith("aiPlat-infra") or path.startswith("aiPlat-infra/"):
        return "infra"
    if path.startswith("aiPlat-core") or path.startswith("aiPlat-core/"):
        return "core"
    if path.startswith("aiPlat-platform") or path.startswith("aiPlat-platform/"):
        return "platform"
    if path.startswith("aiPlat-app") or path.startswith("aiPlat-app/"):
        return "app"
    if path.startswith("aiPlat-management") or path.startswith("aiPlat-management/"):
        return "app"
    return "unknown"


def _content_hash(filepath: Path) -> str:
    """MD5 hash of the first 64KB of a file for precise change detection."""
    try:
        return hashlib.md5(filepath.read_bytes()[:65536]).hexdigest()
    except Exception:
        return ""
