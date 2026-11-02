"""Apply ordered SQL migrations to the standalone eval SQLite DB."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.store.paths import sqlite_path_from_url

STORE_SCHEMA_VERSION = "eval.store.v0"
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_migration_files(migrations_dir: Path | None = None) -> List[Path]:
    root = migrations_dir or _MIGRATIONS_DIR
    if not root.is_dir():
        return []
    return sorted(p for p in root.glob("*.sql") if p.is_file())


def apply_migrations(
    db_url_or_path: str | Path,
    *,
    migrations_dir: Path | None = None,
) -> Dict[str, Any]:
    """Apply pending *.sql migrations; idempotent via eval_schema_migrations.

    Returns summary: {db_path, applied, already, schema_version}.
    """
    if isinstance(db_url_or_path, Path):
        db_path = db_url_or_path.expanduser()
    else:
        raw = str(db_url_or_path).strip()
        db_path = (
            Path(raw).expanduser()
            if "://" not in raw
            else sqlite_path_from_url(raw)
        )
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
        "db_path": str(db_path),
        "applied": applied,
        "already": already,
        "schema_version": STORE_SCHEMA_VERSION,
        "process_split_authorized": False,
    }


def migration_status(db_url_or_path: str | Path) -> Dict[str, Any]:
    """Ensure migrations applied, then list rows (idempotent)."""
    result = apply_migrations(db_url_or_path)
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
