"""Apply ordered SQL migrations to standalone eval SQLite or Postgres."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.store.paths import backend_from_url, postgres_dsn_from_url, redact_db_url, sqlite_path_from_url

STORE_SCHEMA_VERSION = "eval.store.v0"
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_migration_files(migrations_dir: Path | None = None) -> List[Path]:
    root = migrations_dir or _MIGRATIONS_DIR
    if not root.is_dir():
        return []
    return sorted(p for p in root.glob("*.sql") if p.is_file())


def _split_sql_statements(script: str) -> List[str]:
    """Split migration SQL into statements (strip -- line comments)."""
    lines: List[str] = []
    for line in script.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    return [p.strip() for p in text.split(";") if p.strip()]


def _apply_sqlite(
    db_path: Path,
    *,
    migrations_dir: Path | None = None,
) -> Dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    files = _list_migration_files(migrations_dir)
    applied: List[str] = []
    already: List[str] = []

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS eval_schema_migrations ("
            "id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for sql_path in files:
            mid = sql_path.name
            row = conn.execute(
                "SELECT 1 FROM eval_schema_migrations WHERE id=?", (mid,)
            ).fetchone()
            if row:
                already.append(mid)
                continue
            script = sql_path.read_text(encoding="utf-8")
            conn.executescript(script)
            conn.execute(
                "INSERT INTO eval_schema_migrations(id, applied_at) VALUES (?, ?)",
                (mid, _now()),
            )
            applied.append(mid)
        conn.execute(
            "INSERT OR REPLACE INTO eval_store_meta(key, value) VALUES (?, ?)",
            ("schema_version", STORE_SCHEMA_VERSION),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "backend": "sqlite",
        "db_path": str(db_path),
        "db_url": str(db_path),
        "applied": applied,
        "already": already,
        "schema_version": STORE_SCHEMA_VERSION,
        "process_split_authorized": False,
    }


def _apply_postgres(
    dsn: str,
    *,
    migrations_dir: Path | None = None,
    raw_url: str = "",
) -> Dict[str, Any]:
    from app.store.pg_runtime import pg_execute, pg_execute_script, pg_fetchrow

    files = _list_migration_files(migrations_dir)
    applied: List[str] = []
    already: List[str] = []

    pg_execute(
        dsn,
        "CREATE TABLE IF NOT EXISTS eval_schema_migrations ("
        "id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)",
    )
    for sql_path in files:
        mid = sql_path.name
        row = pg_fetchrow(
            dsn, "SELECT 1 AS ok FROM eval_schema_migrations WHERE id=?", (mid,)
        )
        if row:
            already.append(mid)
            continue
        script = sql_path.read_text(encoding="utf-8")
        stmts = _split_sql_statements(script)
        # 0001 also creates eval_schema_migrations — IF NOT EXISTS is fine.
        pg_execute_script(dsn, stmts)
        pg_execute(
            dsn,
            "INSERT INTO eval_schema_migrations(id, applied_at) VALUES (?, ?)",
            (mid, _now()),
        )
        applied.append(mid)

    pg_execute(
        dsn,
        "INSERT INTO eval_store_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        ("schema_version", STORE_SCHEMA_VERSION),
    )

    return {
        "ok": True,
        "backend": "postgres",
        "db_path": redact_db_url(raw_url or dsn),
        "db_url": redact_db_url(raw_url or dsn),
        "applied": applied,
        "already": already,
        "schema_version": STORE_SCHEMA_VERSION,
        "process_split_authorized": False,
    }


def apply_migrations(
    db_url_or_path: str | Path,
    *,
    migrations_dir: Path | None = None,
) -> Dict[str, Any]:
    """Apply pending *.sql migrations; idempotent via eval_schema_migrations.

    Returns summary: {backend, db_path/db_url, applied, already, schema_version}.
    """
    if isinstance(db_url_or_path, Path):
        return _apply_sqlite(db_url_or_path.expanduser(), migrations_dir=migrations_dir)

    raw = str(db_url_or_path).strip()
    if "://" not in raw:
        return _apply_sqlite(Path(raw).expanduser(), migrations_dir=migrations_dir)

    backend = backend_from_url(raw)
    if backend == "postgres":
        dsn = postgres_dsn_from_url(raw)
        return _apply_postgres(dsn, migrations_dir=migrations_dir, raw_url=raw)

    db_path = sqlite_path_from_url(raw)
    return _apply_sqlite(db_path, migrations_dir=migrations_dir)


def migration_status(db_url_or_path: str | Path) -> Dict[str, Any]:
    """Ensure migrations applied, then list rows (idempotent)."""
    result = apply_migrations(db_url_or_path)
    backend = result.get("backend", "sqlite")
    if backend == "postgres":
        from app.store.pg_runtime import pg_fetch

        raw = str(db_url_or_path).strip()
        dsn = postgres_dsn_from_url(raw)
        rows = pg_fetch(
            dsn, "SELECT id, applied_at FROM eval_schema_migrations ORDER BY id"
        )
        migrations = [{"id": r["id"], "applied_at": r["applied_at"]} for r in rows]
        return {
            "ok": True,
            "backend": "postgres",
            "db_path": result["db_path"],
            "db_url": result.get("db_url"),
            "migrations": migrations,
            "schema_version": STORE_SCHEMA_VERSION,
            "process_split_authorized": False,
        }

    db_path = Path(result["db_path"])
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        rows = conn.execute(
            "SELECT id, applied_at FROM eval_schema_migrations ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return {
        "ok": True,
        "backend": "sqlite",
        "db_path": str(db_path),
        "migrations": [{"id": r[0], "applied_at": r[1]} for r in rows],
        "schema_version": STORE_SCHEMA_VERSION,
        "process_split_authorized": False,
    }


def _cli_migrate(db_url: str) -> Dict[str, Any]:
    """CLI entry used by scripts/migrate_local.sh (wires apply + status)."""
    applied = apply_migrations(db_url)
    status = migration_status(db_url)
    return {"apply": applied, "status": status}
