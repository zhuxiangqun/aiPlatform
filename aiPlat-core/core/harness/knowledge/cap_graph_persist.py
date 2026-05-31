"""
Capability Graph SQLite Persistence — survives process restart.

Schema:
  cap_nodes  — agent/skill/tool/MCP/workflow nodes
  cap_edges  — requires/uses/provides/maps_to relationships
  cap_meta   — metadata (last_build timestamp, etc.)

Parallels code_graph_persist.py for consistent architecture.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
        _DB_PATH = os.path.join(home, "cap_graph.db")
    return _DB_PATH


def init_db():
    import sqlite3
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def _get_conn():
    import sqlite3
    return sqlite3.connect(_db_path())


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


def save_graph(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]]):
    import sqlite3
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
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
        conn.commit()
    finally:
        conn.close()


def get_cache_info() -> Dict[str, Any]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM cap_meta WHERE key='last_build'").fetchone()
        last_build = float(row[0]) if row else 0
        count = conn.execute("SELECT COUNT(*) FROM cap_nodes").fetchone()[0]
        return {"last_build": last_build, "nodes": count, "age_seconds": time.time() - last_build if last_build else 0}
    finally:
        conn.close()
