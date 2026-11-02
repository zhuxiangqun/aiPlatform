"""B1-L — live Postgres migrate + roundtrip (compose :5433)."""
from __future__ import annotations

import os

import pytest

from app.store.migrate import apply_migrations
from app.store.paths import backend_from_url
from app.store.store import (
    create_report,
    create_set,
    get_report,
    get_set,
    local_roundtrip,
    open_store,
    store_health,
)

pytestmark = pytest.mark.integration


def _pg_dsn() -> str:
    raw = (os.getenv("AIPLAT_EVAL_PG_DSN") or os.getenv("AIPLAT_EVAL_DB_URL") or "").strip()
    if raw and backend_from_url(raw) == "postgres":
        return raw
    return "postgresql://eval:eval_local@127.0.0.1:5433/eval"


def _pg_reachable(dsn: str) -> bool:
    try:
        from app.store.pg_runtime import pg_fetchval

        pg_fetchval(dsn, "SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def pg_dsn():
    dsn = _pg_dsn()
    if not _pg_reachable(dsn):
        pytest.skip("Postgres not reachable (compose postgres on :5433 or set AIPLAT_EVAL_PG_DSN)")
    return dsn


def test_postgres_migrate_and_roundtrip(pg_dsn: str):
    r1 = apply_migrations(pg_dsn)
    assert r1["ok"] is True
    assert r1["backend"] == "postgres"
    assert r1["process_split_authorized"] is False
    r2 = apply_migrations(pg_dsn)
    assert r2["applied"] == []

    store = open_store(pg_dsn, migrate=True)
    h = store_health(store)
    assert h["ok"] is True
    assert h["backend"] == "postgres"
    assert "***" in h["db_path"] or "postgresql://" in h["db_path"]

    s = create_set(store, name="b1l-pg-set", meta={"phase": "B1-L"}, tenant_id="t-pg")
    assert get_set(store, s["id"])["name"] == "b1l-pg-set"
    r = create_report(store, metrics={"phase": "B1-L"}, tenant_id="t-pg")
    assert get_report(store, r["id"])["metrics"]["phase"] == "B1-L"

    proof = local_roundtrip(store, tenant_id="t-pg")
    assert proof["ok"] is True
    assert proof["backend"] == "postgres"
    assert proof["process_split_authorized"] is False
