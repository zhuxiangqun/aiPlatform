import sqlite3

import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_execution_store_long_term_memory_search_fallback_like(tmp_path):
    """
    Ensure long-term memory search works even if FTS table is missing.
    (search should fallback to LIKE on any exception)
    """
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    rec = await store.add_long_term_memory(user_id="u1", key="k1", content="hello fallback world", metadata={"a": 1})
    assert rec["user_id"] == "u1"

    # Force FTS query to fail by dropping the virtual table.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DROP TABLE IF EXISTS long_term_memories_fts;")
        conn.commit()
    finally:
        conn.close()

    results = await store.search_long_term_memory(user_id="u1", query="fallback", limit=10)
    assert any(r["id"] == rec["id"] for r in results)

