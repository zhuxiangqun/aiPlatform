"""Eval job queue helpers (B2-L enqueue) — sqlite + postgres."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.store.paths import backend_from_url, postgres_dsn_from_url, sqlite_path_from_url

DEFAULT_LEASE_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lease_deadline(seconds: int = DEFAULT_LEASE_SECONDS) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(1, int(seconds)))).isoformat()


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
        "leased_by": _g("leased_by", ""),
        "payload": _loads(_g("payload_json", "{}")),
        "result": _loads(_g("result_json", "{}")),
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
    lease_expires_at: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    now = _now()
    jid = (job_id or "").strip()
    sets = ["status=?", "error_code=?", "error_detail=?", "updated_at=?"]
    args: list[Any] = [status, error_code, error_detail, now]
    if attempts is not None:
        sets.append("attempts=?")
        args.append(int(attempts))
    if lease_expires_at is not None:
        sets.append("lease_expires_at=?")
        args.append(lease_expires_at)
    if result is not None:
        sets.append("result_json=?")
        args.append(_dumps(result))
    args.append(jid)
    sql = f"UPDATE eval_jobs SET {', '.join(sets)} WHERE id=?"

    if backend_from_url(db_url) == "postgres":
        from app.store.pg_runtime import pg_execute

        pg_execute(postgres_dsn_from_url(db_url), sql, tuple(args))
        return get_job(db_url, jid)

    path = sqlite_path_from_url(db_url)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute(sql, tuple(args))
        conn.commit()
    finally:
        conn.close()
    return get_job(db_url, jid)


def claim_next_job(
    db_url: str,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Optional[Dict[str, Any]]:
    """Claim one queued or lease-expired job (PG SKIP LOCKED; SQLite IMMEDIATE)."""
    wid = (worker_id or "").strip() or "worker-local"
    now = _now()
    lease_until = _lease_deadline(lease_seconds)
    max_a = max(1, int(max_attempts))

    if backend_from_url(db_url) == "postgres":
        from app.store.pg_runtime import pg_execute, pg_fetchrow

        dsn = postgres_dsn_from_url(db_url)
        # Exhausted attempts on expired leases → dead_letter before claim.
        pg_execute(
            dsn,
            "UPDATE eval_jobs SET status='dead_letter', error_code='max_attempts', "
            "error_detail='lease reclaim exceeded max_attempts', updated_at=? "
            "WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ? "
            "AND attempts >= ?",
            (now, now, max_a),
        )
        row = pg_fetchrow(
            dsn,
            "WITH cte AS ("
            "  SELECT id FROM eval_jobs "
            "  WHERE status='queued' "
            "     OR (status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?) "
            "  ORDER BY created_at "
            "  FOR UPDATE SKIP LOCKED "
            "  LIMIT 1"
            ") "
            "UPDATE eval_jobs j SET "
            "  status='running', lease_expires_at=?, heartbeat_at=?, leased_by=?, "
            "  attempts=j.attempts + 1, updated_at=? "
            "FROM cte WHERE j.id = cte.id "
            "RETURNING j.*",
            (now, lease_until, now, wid, now),
        )
        return _row_to_job(row) if row else None

    path = sqlite_path_from_url(db_url)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE eval_jobs SET status='dead_letter', error_code='max_attempts', "
            "error_detail='lease reclaim exceeded max_attempts', updated_at=? "
            "WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ? "
            "AND attempts >= ?",
            (now, now, max_a),
        )
        row = conn.execute(
            "SELECT id FROM eval_jobs "
            "WHERE status='queued' "
            "   OR (status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?) "
            "ORDER BY created_at LIMIT 1",
            (now,),
        ).fetchone()
        if not row:
            conn.commit()
            return None
        jid = row["id"]
        conn.execute(
            "UPDATE eval_jobs SET status='running', lease_expires_at=?, heartbeat_at=?, "
            "leased_by=?, attempts=attempts + 1, updated_at=? WHERE id=?",
            (lease_until, now, wid, now, jid),
        )
        conn.commit()
        claimed = conn.execute("SELECT * FROM eval_jobs WHERE id=?", (jid,)).fetchone()
        return _row_to_job(claimed) if claimed else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def heartbeat_job(
    db_url: str,
    job_id: str,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Extend lease if this worker still holds the job."""
    wid = (worker_id or "").strip() or "worker-local"
    jid = (job_id or "").strip()
    now = _now()
    lease_until = _lease_deadline(lease_seconds)

    if backend_from_url(db_url) == "postgres":
        from app.store.pg_runtime import pg_execute

        pg_execute(
            postgres_dsn_from_url(db_url),
            "UPDATE eval_jobs SET lease_expires_at=?, heartbeat_at=?, updated_at=? "
            "WHERE id=? AND status='running' AND leased_by=?",
            (lease_until, now, now, jid, wid),
        )
        return get_job(db_url, jid)

    path = sqlite_path_from_url(db_url)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute(
            "UPDATE eval_jobs SET lease_expires_at=?, heartbeat_at=?, updated_at=? "
            "WHERE id=? AND status='running' AND leased_by=?",
            (lease_until, now, now, jid, wid),
        )
        conn.commit()
    finally:
        conn.close()
    return get_job(db_url, jid)


def _wire_enqueue(db_url: str) -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    return enqueue_job(db_url, runner_id="prompt_eval", tenant_id="t", payload={})


def _wire_claim(db_url: str) -> Optional[Dict[str, Any]]:
    """Same-file caller for method_verify."""
    return claim_next_job(db_url, worker_id="w-verify")
