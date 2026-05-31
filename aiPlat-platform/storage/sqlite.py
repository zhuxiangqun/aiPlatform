import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.api.facades.kb_facade import create_infra_database_client


def _db_path() -> str:
    return os.getenv("AIPLAT_PLATFORM_DB_PATH", "data/aiplat_platform.sqlite3")


_INITED: bool = False


def _connect():
    return create_infra_database_client(_db_path())


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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT DEFAULT '',
              nodes_json TEXT NOT NULL DEFAULT '[]',
              edges_json TEXT NOT NULL DEFAULT '[]',
              data_json TEXT NOT NULL DEFAULT '{}',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflows_name ON workflows(name);")
        # Migration: add enabled column if missing
        try:
            conn.execute("ALTER TABLE workflows ADD COLUMN enabled INTEGER DEFAULT 1")
        except Exception:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_runs (
              workflow_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              run_name TEXT DEFAULT '',
              created_at REAL NOT NULL,
              phase TEXT DEFAULT 'executing',
              PRIMARY KEY (workflow_id, project_id)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_wid ON workflow_runs(workflow_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_pid ON workflow_runs(project_id);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS apps (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              workflow_id TEXT NOT NULL,
              mode TEXT DEFAULT 'chat',
              description TEXT DEFAULT '',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_wid ON apps(workflow_id);")
        # Migration: add capability fields + enabled
        for col, dflt in [("enabled", "INTEGER DEFAULT 1"), ("capability_type", "TEXT DEFAULT ''"), ("capability_id", "TEXT DEFAULT ''")]:
            try:
                conn.execute(f"ALTER TABLE apps ADD COLUMN {col} {dflt}")
            except Exception:
                pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_webhooks (
              app_id TEXT PRIMARY KEY,
              secret TEXT NOT NULL,
              active INTEGER DEFAULT 1
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              node_id TEXT DEFAULT NULL,
              state_json TEXT NOT NULL DEFAULT '{}',
              elapsed REAL DEFAULT 0,
              output TEXT DEFAULT '',
              created_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pe_run_id ON pipeline_events(run_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pe_run_event ON pipeline_events(run_id, created_at DESC);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_versions (
              id TEXT PRIMARY KEY,
              workflow_id TEXT NOT NULL,
              version INTEGER NOT NULL,
              name TEXT NOT NULL,
              nodes_json TEXT NOT NULL DEFAULT '[]',
              edges_json TEXT NOT NULL DEFAULT '[]',
              published_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wv_wid ON workflow_versions(workflow_id);")
        conn.commit()
        _INITED = True
    finally:
        conn.close()


def _row_to_obj(row: Any) -> Dict[str, Any]:
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


def list_tenants(*, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT data_json FROM tenants WHERE status=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (str(status), int(limit), int(offset)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data_json FROM tenants ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (int(limit), int(offset)),
            ).fetchall()
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


def upsert_tenant_by_id(*, tenant_id: str, name: str = "", metadata: Any = None) -> Dict[str, Any]:
    """Convenience wrapper — accepts keyword args like execution_store.upsert_tenant.
    Delegates to upsert_tenant() with a constructed dict."""
    t = {"id": tenant_id, "name": name or tenant_id, "status": "active"}
    if metadata:
        t["metadata"] = metadata
    return upsert_tenant(t)


# -------------------- workflows --------------------


def list_workflows() -> List[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute("SELECT id, name, description, nodes_json, edges_json, created_at, updated_at, coalesce(enabled,1) as enabled FROM workflows ORDER BY updated_at DESC").fetchall()
        return [
            {
                "id": r["id"], "name": r["name"], "description": r["description"] or "",
                "nodes": json.loads(r["nodes_json"]) if r["nodes_json"] else [],
                "edges": json.loads(r["edges_json"]) if r["edges_json"] else [],
                "created_at": r["created_at"], "updated_at": r["updated_at"], "enabled": bool(r["enabled"]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT id, name, description, nodes_json, edges_json, created_at, updated_at, coalesce(enabled,1) as enabled FROM workflows WHERE id=?", (str(workflow_id),)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "name": row["name"], "description": row["description"] or "",
            "nodes": json.loads(row["nodes_json"]) if row["nodes_json"] else [],
            "edges": json.loads(row["edges_json"]) if row["edges_json"] else [],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def create_workflow(workflow_id: str, name: str, description: str, nodes: List[Any], edges: List[Any]) -> Dict[str, Any]:
    init_db()
    conn = _connect()
    now = time.time()
    try:
        conn.execute(
            "INSERT INTO workflows (id, name, description, nodes_json, edges_json, data_json, enabled, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)",
            (str(workflow_id), str(name), str(description or ""), json.dumps(nodes, ensure_ascii=False), json.dumps(edges, ensure_ascii=False), "{}", now, now),
        )
        conn.commit()
        return {
            "id": workflow_id, "name": name, "description": description or "",
            "nodes": nodes, "edges": edges, "created_at": now, "updated_at": now,
        }
    finally:
        conn.close()


def update_workflow(workflow_id: str, name: Optional[str] = None, description: Optional[str] = None, nodes: Optional[List[Any]] = None, edges: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    now = time.time()
    try:
        existing = conn.execute("SELECT * FROM workflows WHERE id=?", (str(workflow_id),)).fetchone()
        if not existing:
            return None
        new_name = name if name is not None else existing["name"]
        new_desc = description if description is not None else (existing["description"] or "")
        new_nodes = json.dumps(nodes, ensure_ascii=False) if nodes is not None else existing["nodes_json"]
        new_edges = json.dumps(edges, ensure_ascii=False) if edges is not None else existing["edges_json"]
        conn.execute(
            "UPDATE workflows SET name=?, description=?, nodes_json=?, edges_json=?, updated_at=? WHERE id=?",
            (str(new_name), str(new_desc), new_nodes, new_edges, now, str(workflow_id)),
        )
        conn.commit()
        return {
            "id": workflow_id, "name": new_name, "description": new_desc,
            "nodes": json.loads(new_nodes) if isinstance(new_nodes, str) else new_nodes,
            "edges": json.loads(new_edges) if isinstance(new_edges, str) else new_edges,
            "updated_at": now,
        }
    finally:
        conn.close()


def delete_workflow(workflow_id: str) -> bool:
    init_db()
    conn = _connect()
    try:
        conn.execute("DELETE FROM workflows WHERE id=?", (str(workflow_id),))
        conn.commit()
        return True
    finally:
        conn.close()


# -------------------- workflow_runs --------------------


def record_workflow_run(workflow_id: str, project_id: str, run_name: str = "") -> None:
    init_db()
    conn = _connect()
    now = time.time()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO workflow_runs (workflow_id, project_id, run_name, created_at, phase) VALUES (?,?,?,?,?)",
            (str(workflow_id), str(project_id), str(run_name or ""), now, "executing"),
        )
        conn.commit()
    finally:
        conn.close()


def update_workflow_run_phase(project_id: str, phase: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute("UPDATE workflow_runs SET phase=? WHERE project_id=?", (str(phase), str(project_id)))
        conn.commit()
    finally:
        conn.close()


def list_workflow_runs(workflow_id: str) -> list:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT project_id, run_name, created_at, phase FROM workflow_runs WHERE workflow_id=? ORDER BY created_at DESC LIMIT 50",
            (str(workflow_id),),
        ).fetchall()
        return [
            {"project_id": r["project_id"], "name": r["run_name"] or "", "created_at": r["created_at"], "phase": r["phase"]}
            for r in rows
        ]
    finally:
        conn.close()


# -------------------- apps --------------------


def list_apps() -> list:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute("SELECT id, name, workflow_id, mode, description, created_at, updated_at FROM apps ORDER BY updated_at DESC").fetchall()
        return [{"id": r["id"], "name": r["name"], "workflow_id": r["workflow_id"], "mode": r["mode"], "description": r["description"] or "", "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]
    finally:
        conn.close()


def get_app(app_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM apps WHERE id=?", (str(app_id),)).fetchone()
        if not row: return None
        return {"id": row["id"], "name": row["name"], "workflow_id": row["workflow_id"], "mode": row["mode"], "description": row["description"] or "", "created_at": row["created_at"], "updated_at": row["updated_at"]}
    finally:
        conn.close()


def create_app(app_id: str, name: str, workflow_id: str, mode: str = "chat", description: str = "") -> Dict[str, Any]:
    init_db()
    conn = _connect()
    now = time.time()
    try:
        conn.execute("INSERT INTO apps (id,name,workflow_id,mode,description,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", (str(app_id), str(name), str(workflow_id), str(mode), str(description or ""), now, now))
        conn.commit()
        return {"id": app_id, "name": name, "workflow_id": workflow_id, "mode": mode, "description": description or "", "created_at": now, "updated_at": now}
    finally:
        conn.close()


def delete_app(app_id: str) -> bool:
    init_db()
    conn = _connect()
    try:
        conn.execute("DELETE FROM apps WHERE id=?", (str(app_id),))
        conn.execute("DELETE FROM app_webhooks WHERE app_id=?", (str(app_id),))
        conn.commit()
        return True
    finally:
        conn.close()


def create_webhook_secret(app_id: str, secret: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute("INSERT OR REPLACE INTO app_webhooks (app_id, secret, active) VALUES (?,?,1)", (str(app_id), str(secret)))
        conn.commit()
    finally:
        conn.close()


def get_webhook_secret(app_id: str) -> Optional[str]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT secret, active FROM app_webhooks WHERE app_id=?", (str(app_id),)).fetchone()
        if row and row["active"]: return row["secret"]
        return None
    finally:
        conn.close()



def toggle_workflow_enabled(workflow_id: str) -> Optional[bool]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT enabled FROM workflows WHERE id=?", (str(workflow_id),)).fetchone()
        if not row: return None
        new_val = 0 if row["enabled"] else 1
        conn.execute("UPDATE workflows SET enabled=? WHERE id=?", (new_val, str(workflow_id)))
        conn.commit()
        return bool(new_val)
    finally:
        conn.close()


# -------------------- pipeline_events --------------------


def insert_pipeline_event(run_id: str, event_type: str, node_id: str = "",
                          state_json: str = "{}", elapsed: float = 0, output: str = "") -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO pipeline_events (run_id, event_type, node_id, state_json, elapsed, output, created_at) VALUES (?,?,?,?,?,?,?)",
            (str(run_id), str(event_type), str(node_id or ""), str(state_json), float(elapsed), str(output or ""), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_event(run_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, run_id, event_type, node_id, state_json, elapsed, output, created_at FROM pipeline_events WHERE run_id=? ORDER BY id DESC LIMIT 1",
            (str(run_id),),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "run_id": row["run_id"], "event_type": row["event_type"],
            "node_id": row["node_id"] or "", "state_json": row["state_json"],
            "elapsed": row["elapsed"], "output": row["output"] or "",
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def list_pipeline_events(run_id: str) -> list:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, run_id, event_type, node_id, state_json, elapsed, output, created_at FROM pipeline_events WHERE run_id=? ORDER BY id ASC",
            (str(run_id),),
        ).fetchall()
        return [
            {"id": r["id"], "run_id": r["run_id"], "event_type": r["event_type"],
             "node_id": r["node_id"] or "", "state_json": r["state_json"],
             "elapsed": r["elapsed"], "output": r["output"] or "",
             "created_at": r["created_at"]}
            for r in rows
        ]
    finally:
        conn.close()

# -------------------- workflow_versions --------------------


def publish_workflow_version(workflow_id, name, nodes, edges):
    init_db()
    conn = _connect()
    now = time.time()
    try:
        import json as _j
        row = conn.execute('SELECT coalesce(max(version),0)+1 as next FROM workflow_versions WHERE workflow_id=?', (str(workflow_id),)).fetchone()
        ver = row['next'] if row else 1
        vid = str(workflow_id) + '_v' + str(ver)
        conn.execute('INSERT INTO workflow_versions (id, workflow_id, version, name, nodes_json, edges_json, published_at) VALUES (?,?,?,?,?,?,?)',
            (vid, str(workflow_id), ver, str(name), _j.dumps(nodes, ensure_ascii=False), _j.dumps(edges, ensure_ascii=False), now))
        conn.commit()
        return {'id': vid, 'workflow_id': workflow_id, 'version': ver, 'name': name, 'published_at': now}
    finally:
        conn.close()


def list_workflow_versions(workflow_id):
    init_db()
    conn = _connect()
    try:
        import json as _j
        rows = conn.execute('SELECT id, workflow_id, version, name, nodes_json, edges_json, published_at FROM workflow_versions WHERE workflow_id=? ORDER BY version DESC LIMIT 20', (str(workflow_id),)).fetchall()
        return [{'id': r['id'], 'workflow_id': r['workflow_id'], 'version': r['version'], 'name': r['name'],
                 'nodes': _j.loads(r['nodes_json']) if r['nodes_json'] else [],
                 'edges': _j.loads(r['edges_json']) if r['edges_json'] else [],
                 'published_at': r['published_at']} for r in rows]
    finally:
        conn.close()


def get_workflow_version(version_id):
    init_db()
    conn = _connect()
    try:
        import json as _j
        r = conn.execute('SELECT id, workflow_id, version, name, nodes_json, edges_json, published_at FROM workflow_versions WHERE id=?', (str(version_id),)).fetchone()
        if not r: return None
        return {'id': r['id'], 'workflow_id': r['workflow_id'], 'version': r['version'], 'name': r['name'],
                'nodes': _j.loads(r['nodes_json']) if r['nodes_json'] else [],
                'edges': _j.loads(r['edges_json']) if r['edges_json'] else [],
                'published_at': r['published_at']}
    finally:
        conn.close()
