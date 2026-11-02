"""A2 — local SQLite migrations + store; no core.harness imports."""
from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import EvalServiceConfig
from app.main import create_app
from app.store.migrate import STORE_SCHEMA_VERSION, apply_migrations, migration_status
from app.store.paths import sqlite_path_from_url
from app.store.store import (
    create_report,
    create_set,
    get_report,
    get_set,
    local_roundtrip,
    open_store,
    store_health,
)


APP_DIR = Path(__file__).resolve().parents[1] / "app"
MIG_DIR = Path(__file__).resolve().parents[1] / "migrations"


def _cfg(tmp_path: Path, *, mode: str = "standalone") -> EvalServiceConfig:
    db = tmp_path / "eval_a2.sqlite3"
    return EvalServiceConfig(
        mode=mode,
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{db}",
        version="0.1.0",
        protocol="eval.protocol.v0",
    )


def test_sqlite_path_from_url_variants(tmp_path: Path):
    p = sqlite_path_from_url(f"sqlite:///{tmp_path / 'x.db'}")
    assert p.name == "x.db"
    bare = sqlite_path_from_url(str(tmp_path / "bare.db"))
    assert bare.name == "bare.db"


def test_apply_migrations_idempotent(tmp_path: Path):
    db = tmp_path / "m.sqlite3"
    r1 = apply_migrations(db, migrations_dir=MIG_DIR)
    assert r1["ok"] is True
    assert "0001_eval_store_v0.sql" in (r1["applied"] + r1["already"])
    assert r1["schema_version"] == STORE_SCHEMA_VERSION
    assert r1["process_split_authorized"] is False

    r2 = apply_migrations(db, migrations_dir=MIG_DIR)
    assert r2["applied"] == []
    assert "0001_eval_store_v0.sql" in r2["already"]

    st = migration_status(db)
    assert any(m["id"] == "0001_eval_store_v0.sql" for m in st["migrations"])


def test_store_roundtrip(tmp_path: Path):
    db_url = f"sqlite:///{tmp_path / 'store.sqlite3'}"
    store = open_store(db_url, migrate=True)
    h = store_health(store)
    assert h["ok"] is True
    assert h["schema_version"] == STORE_SCHEMA_VERSION

    s = create_set(store, name="unit-set", meta={"t": 1})
    assert get_set(store, s["id"])["name"] == "unit-set"
    r = create_report(store, metrics={"score": 0.9})
    assert get_report(store, r["id"])["metrics"]["score"] == 0.9

    proof = local_roundtrip(store)
    assert proof["ok"] is True
    assert proof["process_split_authorized"] is False


def test_readyz_requires_db(tmp_path: Path):
    client = TestClient(create_app(_cfg(tmp_path)))
    rz = client.get("/readyz").json()
    assert rz["status"] == "ready"
    assert rz["db_ok"] is True
    assert rz["store_schema_version"] == STORE_SCHEMA_VERSION
    assert rz["process_split_authorized"] is False

    sh = client.get("/api/platform/apps/eval/store/health").json()
    assert sh["ok"] is True

    rt = client.post("/api/platform/apps/eval/store/roundtrip").json()
    assert rt["ok"] is True
    assert rt["process_split_authorized"] is False


def test_app_sources_forbid_core_private_imports():
    forbidden_prefixes = (
        "core.harness",
        "core.api.core_facade",
        "aiPlat_core",
        "aiplat_core",
        "core.apps.eval",
    )
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    assert not any(
                        name == p or name.startswith(p + ".") for p in forbidden_prefixes
                    ), f"{path} imports {name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                assert not any(
                    mod == p or mod.startswith(p + ".") for p in forbidden_prefixes
                ), f"{path} imports from {mod}"
