import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _db_path() -> str:
    return os.getenv("AIPLAT_APP_DB_PATH", "data/aiplat_app.sqlite3")


_INITED: bool = False


def _connect() -> sqlite3.Connection:
    path = Path(_db_path())
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    global _INITED
    if _INITED:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
              id TEXT PRIMARY KEY,
              name TEXT,
              type TEXT,
              status TEXT,
              data_json TEXT NOT NULL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_channels_status ON channels(status);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY,
              channel_id TEXT,
              user_id TEXT,
              status TEXT,
              data_json TEXT NOT NULL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_channel ON sessions(channel_id);")
        conn.commit()
        _INITED = True
    finally:
        conn.close()


def list_channels(*, status: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        if status:
            rows = conn.execute("SELECT data_json FROM channels WHERE status=? ORDER BY updated_at DESC", (str(status),)).fetchall()
        else:
            rows = conn.execute("SELECT data_json FROM channels ORDER BY updated_at DESC").fetchall()
        return [json.loads(r["data_json"]) for r in rows]
    finally:
        conn.close()


def get_channel(channel_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT data_json FROM channels WHERE id=? LIMIT 1", (str(channel_id),)).fetchone()
        return json.loads(row["data_json"]) if row else None
    finally:
        conn.close()


def upsert_channel(ch: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    now = float(time.time())
    cid = str(ch.get("id"))
    conn = _connect()
    try:
        existing = conn.execute("SELECT created_at FROM channels WHERE id=? LIMIT 1", (cid,)).fetchone()
        created_at = float(existing["created_at"]) if existing else now
        conn.execute(
            """
            INSERT INTO channels(id, name, type, status, data_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              type=excluded.type,
              status=excluded.status,
              data_json=excluded.data_json,
              updated_at=excluded.updated_at;
            """,
            (
                cid,
                str(ch.get("name") or cid),
                str(ch.get("type") or "webhook"),
                str(ch.get("status") or "active"),
                json.dumps(ch, ensure_ascii=False),
                created_at,
                now,
            ),
        )
        conn.commit()
        return ch
    finally:
        conn.close()


def delete_channel(channel_id: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute("DELETE FROM channels WHERE id=?", (str(channel_id),))
        conn.commit()
    finally:
        conn.close()


def list_sessions(*, status: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        if status:
            rows = conn.execute("SELECT data_json FROM sessions WHERE status=? ORDER BY updated_at DESC", (str(status),)).fetchall()
        else:
            rows = conn.execute("SELECT data_json FROM sessions ORDER BY updated_at DESC").fetchall()
        return [json.loads(r["data_json"]) for r in rows]
    finally:
        conn.close()


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT data_json FROM sessions WHERE id=? LIMIT 1", (str(session_id),)).fetchone()
        return json.loads(row["data_json"]) if row else None
    finally:
        conn.close()


def upsert_session(s: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    now = float(time.time())
    sid = str(s.get("id"))
    conn = _connect()
    try:
        existing = conn.execute("SELECT created_at FROM sessions WHERE id=? LIMIT 1", (sid,)).fetchone()
        created_at = float(existing["created_at"]) if existing else now
        conn.execute(
            """
            INSERT INTO sessions(id, channel_id, user_id, status, data_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              channel_id=excluded.channel_id,
              user_id=excluded.user_id,
              status=excluded.status,
              data_json=excluded.data_json,
              updated_at=excluded.updated_at;
            """,
            (
                sid,
                s.get("channel_id"),
                s.get("user_id"),
                str(s.get("status") or "active"),
                json.dumps(s, ensure_ascii=False),
                created_at,
                now,
            ),
        )
        conn.commit()
        return s
    finally:
        conn.close()

