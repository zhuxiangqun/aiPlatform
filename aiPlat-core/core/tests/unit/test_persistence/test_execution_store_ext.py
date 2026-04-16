import sqlite3
import time

import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_schema_version_is_current(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()
    ver = await store.get_schema_version()
    assert ver == store.CURRENT_SCHEMA_VERSION


@pytest.mark.asyncio
async def test_legacy_db_without_meta_is_upgraded(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE agent_executions (
              id TEXT PRIMARY KEY,
              agent_id TEXT NOT NULL,
              status TEXT NOT NULL,
              input_json TEXT,
              output_json TEXT,
              error TEXT,
              start_time REAL,
              end_time REAL,
              duration_ms INTEGER,
              created_at REAL NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()
    assert await store.get_schema_version() == store.CURRENT_SCHEMA_VERSION


@pytest.mark.asyncio
async def test_retention_prune_by_days(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    now = time.time()
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path), retention_days=3, prune_on_start=False))
    await store.init()

    conn = sqlite3.connect(str(db_path))
    try:
        # old (10 days ago)
        conn.execute(
            """
            INSERT INTO agent_executions
              (id, agent_id, status, input_json, output_json, error, start_time, end_time, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("old", "a1", "completed", "{}", "{}", None, now - 10, now - 10, 1, now - 10 * 86400),
        )
        # new
        conn.execute(
            """
            INSERT INTO agent_executions
              (id, agent_id, status, input_json, output_json, error, start_time, end_time, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("new", "a1", "completed", "{}", "{}", None, now, now, 1, now),
        )
        conn.commit()
    finally:
        conn.close()

    await store.prune(now_ts=now)

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT id FROM agent_executions ORDER BY id").fetchall()
        ids = [r[0] for r in rows]
        assert ids == ["new"]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_graph_run_checkpoint_roundtrip(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    run_id = await store.start_graph_run("test_graph", initial_state={"x": 1})
    ckpt_id = await store.add_graph_checkpoint(run_id=run_id, step=1, state={"step_count": 1, "foo": "bar"})
    await store.finish_graph_run(run_id=run_id, status="completed", final_state={"ok": True}, summary={"s": 1})

    cps = await store.list_graph_checkpoints(run_id)
    assert len(cps) == 1
    assert cps[0]["checkpoint_id"] == ckpt_id
    assert cps[0]["state"]["foo"] == "bar"
