"""Postgres-backed EvalStore (B1-L) — same surface as SQLite store."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.store.migrate import STORE_SCHEMA_VERSION
from app.store.paths import postgres_dsn_from_url, redact_db_url
from app.store.pg_runtime import pg_execute, pg_fetch, pg_fetchrow, pg_fetchval


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _dumps(obj: Any) -> str:
    return json.dumps(obj if obj is not None else {}, ensure_ascii=False)


def _loads(raw: Any, default: Any = None) -> Any:
    if raw is None or raw == "":
        return {} if default is None else default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return {} if default is None else default


class _PgEvalStore:
    """asyncpg-backed standalone eval store (charter eval.store.v0)."""

    def __init__(self, dsn: str, *, display_url: str = ""):
        self.dsn = dsn
        self.display_url = display_url or redact_db_url(dsn)
        self.db_path = self.display_url  # health field parity with sqlite
        self.backend = "postgres"

    def _health(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for table in (
            "eval_sets",
            "eval_tasks",
            "eval_runs",
            "eval_judgments",
            "eval_labels",
            "eval_reports",
            "eval_judges",
            "eval_gates",
        ):
            counts[table] = int(
                pg_fetchval(self.dsn, f"SELECT COUNT(*) FROM {table}") or 0
            )
        ver = pg_fetchrow(
            self.dsn, "SELECT value FROM eval_store_meta WHERE key=?", ("schema_version",)
        )
        return {
            "ok": True,
            "backend": "postgres",
            "schema_version": (ver["value"] if ver else STORE_SCHEMA_VERSION),
            "db_path": self.display_url,
            "db_url": self.display_url,
            "counts": counts,
            "process_split_authorized": False,
        }

    def _create_set(
        self,
        *,
        name: str,
        version: str = "0",
        split: str = "dev",
        meta: Optional[Dict[str, Any]] = None,
        set_id: Optional[str] = None,
        tenant_id: str = "",
    ) -> Dict[str, Any]:
        sid = set_id or _new_id("set")
        now = _now()
        tid = (tenant_id or "").strip()
        pg_execute(
            self.dsn,
            "INSERT INTO eval_sets(id, name, version, split, meta_json, created_at, updated_at, tenant_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, name, version, split, _dumps(meta or {}), now, now, tid),
        )
        return self._get_set(sid) or {"id": sid}

    def _get_set(self, set_id: str) -> Optional[Dict[str, Any]]:
        row = pg_fetchrow(self.dsn, "SELECT * FROM eval_sets WHERE id=?", (set_id,))
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "version": row["version"],
            "split": row["split"],
            "meta": _loads(row["meta_json"]),
            "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _list_sets(self, *, limit: int = 100, tenant_id: str = "") -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit), 1000))
        tid = (tenant_id or "").strip()
        if tid:
            rows = pg_fetch(
                self.dsn,
                "SELECT id FROM eval_sets WHERE tenant_id=? ORDER BY updated_at DESC LIMIT ?",
                (tid, lim),
            )
        else:
            rows = pg_fetch(
                self.dsn,
                "SELECT id FROM eval_sets ORDER BY updated_at DESC LIMIT ?",
                (lim,),
            )
        out: List[Dict[str, Any]] = []
        for row in rows:
            got = self._get_set(row["id"])
            if got:
                out.append(got)
        return out

    def _create_report(
        self,
        *,
        run_ids: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        slices: Optional[Dict[str, Any]] = None,
        failures: Optional[List[Any]] = None,
        report_id: Optional[str] = None,
        tenant_id: str = "",
    ) -> Dict[str, Any]:
        rid = report_id or _new_id("rpt")
        now = _now()
        tid = (tenant_id or "").strip()
        pg_execute(
            self.dsn,
            "INSERT INTO eval_reports(id, run_ids_json, metrics_json, slices_json, "
            "failures_json, created_at, tenant_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                rid,
                _dumps(list(run_ids or [])),
                _dumps(metrics or {}),
                _dumps(slices or {}),
                _dumps(list(failures or [])),
                now,
                tid,
            ),
        )
        return self._get_report(rid) or {"id": rid}

    def _get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        row = pg_fetchrow(self.dsn, "SELECT * FROM eval_reports WHERE id=?", (report_id,))
        if not row:
            return None
        return {
            "id": row["id"],
            "run_ids": _loads(row["run_ids_json"], []),
            "metrics": _loads(row["metrics_json"]),
            "slices": _loads(row["slices_json"]),
            "failures": _loads(row["failures_json"], []),
            "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else "",
            "created_at": row["created_at"],
        }

    def _list_reports(self, *, limit: int = 100, tenant_id: str = "") -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit), 1000))
        tid = (tenant_id or "").strip()
        if tid:
            rows = pg_fetch(
                self.dsn,
                "SELECT id FROM eval_reports WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                (tid, lim),
            )
        else:
            rows = pg_fetch(
                self.dsn,
                "SELECT id FROM eval_reports ORDER BY created_at DESC LIMIT ?",
                (lim,),
            )
        out: List[Dict[str, Any]] = []
        for row in rows:
            got = self._get_report(row["id"])
            if got:
                out.append(got)
        return out


PgEvalStore = _PgEvalStore


def open_pg_store(db_url: str) -> PgEvalStore:
    dsn = postgres_dsn_from_url(db_url)
    store = _PgEvalStore(dsn, display_url=redact_db_url(db_url))
    _ = store._health()
    return store


def _wire_open_pg(db_url: str) -> PgEvalStore:
    """Same-file caller for method_verify."""
    return open_pg_store(db_url)
