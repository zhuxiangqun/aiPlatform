"""
Capability Graph SQLite Persistence — survives process restart.

Schema:
  cap_nodes  — agent/skill/tool/MCP/workflow nodes
  cap_edges  — requires/uses/provides/maps_to relationships
  cap_meta   — metadata (last_build timestamp, etc.)

Parallels code_graph_persist.py for consistent architecture.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_FP_SCHEMA = "cap_graph_fp_v1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cap_nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    label TEXT NOT NULL,
    agent_type TEXT DEFAULT '',
    status TEXT DEFAULT '',
    category TEXT DEFAULT '',
    path TEXT DEFAULT '',
    mtime REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cap_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'requires'
);

CREATE INDEX IF NOT EXISTS idx_cap_edges_from ON cap_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_cap_edges_to ON cap_edges(to_id);

CREATE TABLE IF NOT EXISTS cap_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_DB_PATH: Optional[str] = None


def _db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        # AIPLAT_HOME 优先（配置驱动，§5；复用权威路径解析，防路径漂移）
        from core.utils.paths import get_aiplat_home
        _DB_PATH = os.path.join(get_aiplat_home(), "cap_graph.db")
    return _DB_PATH


def init_db():
    import sqlite3
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def _get_conn():
    import sqlite3
    return sqlite3.connect(_db_path(), timeout=5.0)


def has_cache() -> bool:
    if not os.path.exists(_db_path()):
        return False
    conn = _get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM cap_nodes").fetchone()[0]
        return count > 0
    finally:
        conn.close()


def load_nodes() -> Dict[str, Dict[str, Any]]:
    conn = _get_conn()
    try:
        nodes: Dict[str, Dict[str, Any]] = {}
        rows = conn.execute("SELECT id, type, label, agent_type, status, category, path, mtime FROM cap_nodes").fetchall()
        for nid, ntype, label, atype, status, cat, path, mtime in rows:
            nodes[nid] = {
                "id": nid, "type": ntype, "label": label,
                "agent_type": atype, "status": status, "category": cat,
                "path": path, "_mtime": mtime,
                "in_degree": 0, "out_degree": 0,
            }
        return nodes
    finally:
        conn.close()


def load_edges() -> List[Dict[str, str]]:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT from_id, to_id, relation FROM cap_edges").fetchall()
        return [{"from": r[0], "to": r[1], "relation": r[2]} for r in rows]
    finally:
        conn.close()


def compute_source_fingerprint(nodes: Dict[str, Dict[str, Any]]) -> str:
    """Stable fingerprint from node ids + paths (not mtime alone). Fail → raise."""
    parts = []
    for nid in sorted(nodes.keys()):
        n = nodes[nid]
        parts.append(f"{nid}|{n.get('type','')}|{n.get('path','')}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{_FP_SCHEMA}|n={len(nodes)}|{digest}"


def get_meta(key: str) -> Optional[str]:
    if not os.path.exists(_db_path()):
        return None
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM cap_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def evaluate_freshness(nodes: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Return freshness verdict. Missing meta / unreadable / calc fail → stale=True."""
    stored = get_meta("source_fingerprint")
    if not stored:
        return {"stale": True, "reason": "missing_fingerprint_meta", "stored": None, "computed": None}
    if nodes is None:
        try:
            nodes = load_nodes()
        except Exception as e:
            logging.getLogger("cap_graph_persist").warning("fingerprint load failed: %s", e)
            return {"stale": True, "reason": "source_unreadable", "stored": stored, "computed": None}
    try:
        computed = compute_source_fingerprint(nodes)
    except Exception as e:
        logging.getLogger("cap_graph_persist").warning("fingerprint compute failed: %s", e)
        return {"stale": True, "reason": "fingerprint_compute_failed", "stored": stored, "computed": None}
    stale = stored != computed
    return {
        "stale": stale,
        "reason": "mismatch" if stale else "ok",
        "stored": stored,
        "computed": computed,
    }


def save_graph(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    import sqlite3
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("DELETE FROM cap_nodes")
        conn.execute("DELETE FROM cap_edges")

        now = time.time()
        for nid, n in nodes.items():
            conn.execute(
                "INSERT OR REPLACE INTO cap_nodes (id, type, label, agent_type, status, category, path, mtime) VALUES (?,?,?,?,?,?,?,?)",
                (nid, n.get("type", ""), n.get("label", nid),
                 n.get("agent_type", ""), n.get("status", ""),
                 n.get("category", ""), n.get("path", ""), 0)
            )
        for e in edges:
            conn.execute(
                "INSERT INTO cap_edges (from_id, to_id, relation) VALUES (?,?,?)",
                (e["from"], e["to"], e.get("relation", "requires"))
            )
        conn.execute("INSERT OR REPLACE INTO cap_meta (key, value) VALUES ('last_build', ?)", (str(now),))
        try:
            fp = compute_source_fingerprint(nodes)
            conn.execute(
                "INSERT OR REPLACE INTO cap_meta (key, value) VALUES ('source_fingerprint', ?)",
                (fp,),
            )
        except Exception as e:
            logging.getLogger("cap_graph_persist").warning("fingerprint save skipped: %s", e)
        conn.commit()
    finally:
        conn.close()


def get_cache_info() -> Dict[str, Any]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM cap_meta WHERE key='last_build'").fetchone()
        last_build = float(row[0]) if row else 0
        count = conn.execute("SELECT COUNT(*) FROM cap_nodes").fetchone()[0]
        fp_row = conn.execute(
            "SELECT value FROM cap_meta WHERE key='source_fingerprint'"
        ).fetchone()
        info = {
            "last_build": last_build,
            "nodes": count,
            "age_seconds": time.time() - last_build if last_build else 0,
            "source_fingerprint": fp_row[0] if fp_row else None,
            "stale": fp_row is None,  # missing meta ⇒ stale; callers may re-evaluate
        }
        return info
    finally:
        conn.close()
