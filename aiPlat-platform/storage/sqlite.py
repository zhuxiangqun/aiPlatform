import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _db_path() -> str:
    return os.getenv("AIPLAT_PLATFORM_DB_PATH", "data/aiplat_platform.sqlite3")


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
            CREATE TABLE IF NOT EXISTS gateway_routes (
              id TEXT PRIMARY KEY,
              name TEXT,
              path TEXT,
              backend TEXT,
              enabled INTEGER,
              data_json TEXT NOT NULL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gateway_routes_enabled ON gateway_routes(enabled);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
              id TEXT PRIMARY KEY,
              username TEXT,
              email TEXT,
              role TEXT,
              status TEXT,
              data_json TEXT NOT NULL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth_users(role);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_users_status ON auth_users(status);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
              id TEXT PRIMARY KEY,
              name TEXT,
              status TEXT,
              data_json TEXT NOT NULL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);")
        conn.commit()
        _INITED = True
    finally:
        conn.close()


def _row_to_obj(row: sqlite3.Row) -> Dict[str, Any]:
    data = json.loads(row["data_json"]) if row["data_json"] else {}
    if isinstance(data, dict):
        return data
    return {"data": data}


# -------------------- gateway_routes --------------------


def list_gateway_routes(*, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        if enabled is None:
            rows = conn.execute("SELECT data_json FROM gateway_routes ORDER BY updated_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT data_json FROM gateway_routes WHERE enabled=? ORDER BY updated_at DESC", (1 if enabled else 0,)
            ).fetchall()
        return [json.loads(r["data_json"]) for r in rows]
    finally:
        conn.close()


def get_gateway_route(route_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT data_json FROM gateway_routes WHERE id=? LIMIT 1", (str(route_id),)).fetchone()
        return json.loads(row["data_json"]) if row else None
    finally:
        conn.close()


def upsert_gateway_route(route: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    now = float(time.time())
    rid = str(route.get("id"))
    conn = _connect()
    try:
        existing = conn.execute("SELECT created_at FROM gateway_routes WHERE id=? LIMIT 1", (rid,)).fetchone()
        created_at = float(existing["created_at"]) if existing else now
        enabled = 1 if bool(route.get("enabled", True)) else 0
        conn.execute(
            """
            INSERT INTO gateway_routes(id, name, path, backend, enabled, data_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              path=excluded.path,
              backend=excluded.backend,
              enabled=excluded.enabled,
              data_json=excluded.data_json,
              updated_at=excluded.updated_at;
            """,
            (
                rid,
                str(route.get("name") or rid),
                str(route.get("path") or "/"),
                str(route.get("backend") or "core"),
                enabled,
                json.dumps(route, ensure_ascii=False),
                created_at,
                now,
            ),
        )
        conn.commit()
        return route
    finally:
        conn.close()


def delete_gateway_route(route_id: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute("DELETE FROM gateway_routes WHERE id=?", (str(route_id),))
        conn.commit()
    finally:
        conn.close()


# -------------------- auth_users --------------------


def list_auth_users(*, role: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        clauses = ["1=1"]
        params: list = []
        if role:
            clauses.append("role=?")
            params.append(str(role))
        if status:
            clauses.append("status=?")
            params.append(str(status))
        where = " AND ".join(clauses)
        rows = conn.execute(f"SELECT data_json FROM auth_users WHERE {where} ORDER BY updated_at DESC", params).fetchall()
        return [json.loads(r["data_json"]) for r in rows]
    finally:
        conn.close()


def get_auth_user(user_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT data_json FROM auth_users WHERE id=? LIMIT 1", (str(user_id),)).fetchone()
        return json.loads(row["data_json"]) if row else None
    finally:
        conn.close()


def upsert_auth_user(user: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    now = float(time.time())
    uid = str(user.get("id"))
    conn = _connect()
    try:
        existing = conn.execute("SELECT created_at FROM auth_users WHERE id=? LIMIT 1", (uid,)).fetchone()
        created_at = float(existing["created_at"]) if existing else now
        conn.execute(
            """
            INSERT INTO auth_users(id, username, email, role, status, data_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              username=excluded.username,
              email=excluded.email,
              role=excluded.role,
              status=excluded.status,
              data_json=excluded.data_json,
              updated_at=excluded.updated_at;
            """,
            (
                uid,
                str(user.get("username") or uid),
                str(user.get("email") or ""),
                str(user.get("role") or "user"),
                str(user.get("status") or "active"),
                json.dumps(user, ensure_ascii=False),
                created_at,
                now,
            ),
        )
        conn.commit()
        return user
    finally:
        conn.close()


def delete_auth_user(user_id: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute("DELETE FROM auth_users WHERE id=?", (str(user_id),))
        conn.commit()
    finally:
        conn.close()


# -------------------- tenants --------------------


def list_tenants(*, status: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        if status:
            rows = conn.execute("SELECT data_json FROM tenants WHERE status=? ORDER BY updated_at DESC", (str(status),)).fetchall()
        else:
            rows = conn.execute("SELECT data_json FROM tenants ORDER BY updated_at DESC").fetchall()
        return [json.loads(r["data_json"]) for r in rows]
    finally:
        conn.close()


def get_tenant(tenant_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT data_json FROM tenants WHERE id=? LIMIT 1", (str(tenant_id),)).fetchone()
        return json.loads(row["data_json"]) if row else None
    finally:
        conn.close()


def upsert_tenant(tenant: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    now = float(time.time())
    tid = str(tenant.get("id"))
    conn = _connect()
    try:
        existing = conn.execute("SELECT created_at FROM tenants WHERE id=? LIMIT 1", (tid,)).fetchone()
        created_at = float(existing["created_at"]) if existing else now
        conn.execute(
            """
            INSERT INTO tenants(id, name, status, data_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              status=excluded.status,
              data_json=excluded.data_json,
              updated_at=excluded.updated_at;
            """,
            (
                tid,
                str(tenant.get("name") or tid),
                str(tenant.get("status") or "active"),
                json.dumps(tenant, ensure_ascii=False),
                created_at,
                now,
            ),
        )
        conn.commit()
        return tenant
    finally:
        conn.close()


def delete_tenant(tenant_id: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute("DELETE FROM tenants WHERE id=?", (str(tenant_id),))
        conn.commit()
    finally:
        conn.close()

