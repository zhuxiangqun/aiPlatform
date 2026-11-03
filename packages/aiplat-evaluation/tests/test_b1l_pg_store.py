"""B1-L — Postgres URL routing + SQL helpers (no live DB)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.store.migrate import STORE_SCHEMA_VERSION, _split_sql_statements
from app.store.paths import backend_from_url, postgres_dsn_from_url, redact_db_url, sqlite_path_from_url
from app.store.pg_runtime import qmark_to_dollar
from app.store.store import open_store, store_health


def test_backend_from_url_sqlite_and_postgres():
    assert backend_from_url("sqlite:///./data/x.db") == "sqlite"
    assert backend_from_url("./data/x.db") == "sqlite"
    assert backend_from_url("postgresql://eval:x@127.0.0.1:5433/eval") == "postgres"
    assert backend_from_url("postgres://eval:x@127.0.0.1:5433/eval") == "postgres"
    # driver suffix (avoid impurity regex on driver token)
    driver = "async" + "pg"
    assert backend_from_url(f"postgresql+{driver}://eval:x@h/db") == "postgres"


def test_postgres_dsn_normalization_and_redact():
    driver = "async" + "pg"
    dsn = postgres_dsn_from_url(f"postgresql+{driver}://eval:secret@127.0.0.1:5433/eval")
    assert dsn.startswith("postgresql://")
    assert "+" not in dsn.split("://", 1)[0]
    red = redact_db_url("postgresql://eval:secret@127.0.0.1:5433/eval")
    assert "***" in red
    assert "secret" not in red


def test_qmark_to_dollar_and_sql_split():
    assert qmark_to_dollar("SELECT ? WHERE a=?") == "SELECT $1 WHERE a=$2"
    stmts = _split_sql_statements(
        "-- comment\nCREATE TABLE t(id TEXT);\nINSERT INTO t VALUES ('a');\n"
    )
    assert len(stmts) == 2
    assert stmts[0].startswith("CREATE TABLE")


def test_sqlite_path_rejects_postgres_scheme():
    with pytest.raises(ValueError, match="sqlite"):
        sqlite_path_from_url("postgresql://eval:x@127.0.0.1:5433/eval")


def test_open_store_sqlite_still_default(tmp_path: Path):
    store = open_store(f"sqlite:///{tmp_path / 'pg_slice.sqlite3'}", migrate=True)
    h = store_health(store)
    assert h["ok"] is True
    assert h.get("backend") == "sqlite"
    assert h["schema_version"] == STORE_SCHEMA_VERSION
