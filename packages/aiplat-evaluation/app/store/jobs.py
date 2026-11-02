"""Eval job queue helpers (B2-L enqueue) — sqlite + postgres."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.store.paths import backend_from_url, postgres_dsn_from_url, sqlite_path_from_url


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"job_{uuid.uuid4().hex[:16]}"


def _dumps(obj: Any) -> str:
    return json.dumps(obj if obj is not None else {}, ensure_ascii=False)


def _loads(raw: Any) -> Dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(str(raw))
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _row_to_job(row: Any) -> Dict[str, Any]:
    keys = row.keys() if hasattr(row, "keys") else []
    get = row.__getitem__

    def _g(name: str, default: Any = "") -> Any:
        if keys and name not in keys:
            return default
        try:
            return get(name)
        except Exception:
            return default

    return {
        "job_id": _g("id"),
        "tenant_id": _g("tenant_id", ""),
        "runner_id": _g("runner_id"),
        "idempotency_key": _g("idempotency_key", ""),
        "status": _g("status", "queued"),
        "attempts": int(_g("attempts", 0) or 0),
        "lease_expires_at": _g("lease_expires_at"),
        "heartbeat_at": _g("heartbeat_at"),
        "payload": _loads(_g("payload_json", "{}")),
        "error_code": _g("error_code", ""),
        "error_detail": _g("error_detail", ""),
        "created_at": _g("created_at"),
        "updated_at": _g("updated_at"),
        "process_split_authorized": False,
    }


def enqueue_job(
    db_url: str,
    *,
    runner_id: str,
    tenant_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
    idempotency_key: str = "",
) -> Dict[str, Any]:
    """Insert queued job; same tenant+idempotency_key returns existing row."""
    tid = (tenant_id or "").strip()
    key = (idempotency_key or "").strip()
    rid = (runner_id or "").strip()
    if key:
        existing = find_job_by_idempotency(db_url, tenant_id=tid, idempotency_key=key)
        if existing:
            return existing

    job_id = _new_id()
    now = _now()
    payload_json = _dumps(payload or {})

    if backend_from_url(db_url) == "postgres":
        from app.store.pg_runtime import pg_execute, pg_fetchrow

        dsn = postgres_dsn_from_url(db_url)
        pg_execute(
            dsn,
            "INSERT INTO eval_jobs(id, tenant_id, runner_id, idempotency_key, status, attempts, "
            "payload_json, error_code, error_detail, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'queued', 0, ?, '', '', ?, ?)",
            (job_id, tid, rid, key, payload_json, now, now),
        )
        row = pg_fetchrow(dsn, "SELECT * FROM eval_jobs WHERE id=?", (job_id,))
        return _row_to_job(row)

    path = sqlite_path_from_url(db_url)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO eval_jobs(id, tenant_id, runner_id, idempotency_key, status, attempts, "
            "payload_json, error_code, error_detail, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'queued', 0, ?, '', '', ?, ?)",
            (job_id, tid, rid, key, payload_json, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM eval_jobs WHERE id=?", (job_id,)).fetchone()
        return _row_to_job(row)
    finally:
        conn.close()


def find_job_by_idempotency(
    db_url: str, *, tenant_id: str, idempotency_key: str
) -> Optional[Dict[str, Any]]:
    tid = (tenant_id or "").strip()
    key = (idempotency_key or "").strip()
    if not key:
        return None
    if backend_from_url(db_url) == "postgres":
        from app.store.pg_runtime import pg_fetchrow

        dsn = postgres_dsn_from_url(db_url)
        row = pg_fetchrow(
            dsn,
            "SELECT * FROM eval_jobs WHERE tenant_id=? AND idempotency_key=? "
            "ORDER BY created_at DESC LIMIT 1",
            (tid, key),
        )
        return _row_to_job(row) if row else None

    path = sqlite_path_from_url(db_url)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM eval_jobs WHERE tenant_id=? AND idempotency_key=? "
            "ORDER BY created_at DESC LIMIT 1",
            (tid, key),
        ).fetchone()
        return _row_to_job(row) if row else None
    finally:
        conn.close()


def get_job(db_url: str, job_id: str) -> Optional[Dict[str, Any]]:
    jid = (job_id or "").strip()
    if not jid:
        return None
    if backend_from_url(db_url) == "postgres":
        from app.store.pg_runtime import pg_fetchrow

        row = pg_fetchrow(
            postgres_dsn_from_url(db_url), "SELECT * FROM eval_jobs WHERE id=?", (jid,)
        )
        return _row_to_job(row) if row else None

    path = sqlite_path_from_url(db_url)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM eval_jobs WHERE id=?", (jid,)).fetchone()
        return _row_to_job(row) if row else None
    finally:
        conn.close()


def update_job_status(
    db_url: str,
    job_id: str,
    *,
    status: str,
    error_code: str = "",
    error_detail: str = "",
    attempts: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    now = _now()
    jid = (job_id or "").strip()
    if backend_from_url(db_url) == "postgres":
        from app.store.pg_runtime import pg_execute

        dsn = postgres_dsn_from_url(db_url)
        if attempts is None:
            pg_execute(
                dsn,
                "UPDATE eval_jobs SET status=?, error_code=?, error_detail=?, updated_at=? WHERE id=?",
                (status, error_code, error_detail, now, jid),
            )
        else:
            pg_execute(
                dsn,
                "UPDATE eval_jobs SET status=?, error_code=?, error_detail=?, attempts=?, updated_at=? WHERE id=?",
                (status, error_code, error_detail, int(attempts), now, jid),
            )
        return get_job(db_url, jid)

    path = sqlite_path_from_url(db_url)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        if attempts is None:
            conn.execute(
                "UPDATE eval_jobs SET status=?, error_code=?, error_detail=?, updated_at=? WHERE id=?",
                (status, error_code, error_detail, now, jid),
            )
        else:
            conn.execute(
                "UPDATE eval_jobs SET status=?, error_code=?, error_detail=?, attempts=?, updated_at=? WHERE id=?",
                (status, error_code, error_detail, int(attempts), now, jid),
            )
        conn.commit()
    finally:
        conn.close()
    return get_job(db_url, jid)


def _wire_enqueue(db_url: str) -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    return enqueue_job(db_url, runner_id="prompt_eval", tenant_id="t", payload={})
