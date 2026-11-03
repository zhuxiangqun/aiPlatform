"""prompt_eval_ops sync CRUD — platform route is facade-only."""
from __future__ import annotations

from pathlib import Path

import pytest


def _schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS prompt_test_cases (
            id TEXT PRIMARY KEY,
            template_id TEXT NOT NULL,
            name TEXT,
            variables TEXT,
            expected_keys TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS prompt_eval_runs (
            id TEXT PRIMARY KEY,
            template_id TEXT,
            version_a TEXT,
            version_b TEXT,
            model TEXT,
            status TEXT,
            total_cases INTEGER,
            results_json TEXT,
            a_wins INTEGER,
            b_wins INTEGER,
            draws INTEGER,
            avg_score_a REAL,
            avg_score_b REAL,
            created_at REAL,
            finished_at REAL
        );
        """
    )
    conn.commit()


@pytest.mark.integration
def test_prompt_eval_ops_crud(tmp_path: Path, monkeypatch):
    db = tmp_path / "exec.sqlite3"
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _schema(conn)
    conn.close()

    from core.apps.eval.service import prompt_eval_ops as ops

    # Patch get_db_connection to use our file
    class _CM:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            c = sqlite3.connect(self.path)
            c.row_factory = sqlite3.Row
            return c

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "core.api.core_facade.get_db_connection",
        lambda path: _CM(str(db)),
    )

    created = ops.prompt_eval_create_test_case(
        db_path=str(db),
        template_id="tpl1",
        name="c1",
        variables={"x": 1},
        expected_keys="ok",
    )
    assert created["id"].startswith("tc-")
    listed = ops.prompt_eval_list_test_cases(db_path=str(db), template_id="tpl1")
    assert listed["total"] == 1
    ops.prompt_eval_update_test_case(
        db_path=str(db),
        case_id=created["id"],
        name="c1b",
        variables=None,
        expected_keys=None,
    )
    ops.prompt_eval_delete_test_case(db_path=str(db), case_id=created["id"])
    assert ops.prompt_eval_list_test_cases(db_path=str(db))["total"] == 0


def test_platform_prompt_eval_is_thin():
    plat = (
        Path(__file__).resolve().parents[3].parent
        / "aiPlat-platform"
        / "apps"
        / "eval"
        / "api"
        / "prompt_eval.py"
    )
    text = plat.read_text(encoding="utf-8")
    assert "sqlite3" not in text
    assert "get_db_connection" not in text
    assert "prompt_eval_list_test_cases" in text
