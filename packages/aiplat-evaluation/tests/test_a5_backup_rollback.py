"""A5 — local SQLite backup / rollback (no Central)."""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from app.store import create_report, create_set, get_report, open_store
from app.store.paths import sqlite_path_from_url


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_backup_and_rollback_scripts(tmp_path: Path):
    db = tmp_path / "eval.sqlite3"
    db_url = f"sqlite:///{db}"
    backup_dir = tmp_path / "backups"
    store = open_store(db_url, migrate=True)
    s = create_set(store, name="a5-bak")
    r = create_report(store, metrics={"k": 1})
    rid = r["id"]

    env = os.environ.copy()
    env["AIPLAT_EVAL_DB_URL"] = db_url
    env["AIPLAT_EVAL_BACKUP_DIR"] = str(backup_dir)
    env["PYTHONPATH"] = str(ROOT)
    subprocess.check_call(["bash", str(ROOT / "scripts/backup_local.sh")], env=env, cwd=str(ROOT))
    sqls = list(backup_dir.glob("eval_local-*.sql"))
    assert sqls, "expected sql backup"

    # wipe
    with sqlite3.connect(str(db)) as c:
        c.execute("DELETE FROM eval_reports")
        c.commit()
    assert get_report(open_store(db_url, migrate=False), rid) is None

    subprocess.check_call(
        ["bash", str(ROOT / "scripts/rollback_local.sh"), str(sqls[0])],
        env=env,
        cwd=str(ROOT),
    )
    restored = get_report(open_store(db_url, migrate=True), rid)
    assert restored is not None
    assert restored["id"] == rid
    assert s["id"]
    assert sqlite_path_from_url(db_url) == db
