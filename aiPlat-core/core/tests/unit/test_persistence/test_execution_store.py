import time

import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_execution_store_agent_roundtrip(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    now = time.time()
    record = {
        "id": "exec_1",
        "agent_id": "agent_1",
        "status": "completed",
        "input": {"q": "hello"},
        "output": {"a": "world"},
        "error": None,
        "start_time": now,
        "end_time": now + 0.1,
        "duration_ms": 100,
    }

    await store.upsert_agent_execution(record)

    got = await store.get_agent_execution("exec_1")
    assert got is not None
    assert got["id"] == "exec_1"
    assert got["agent_id"] == "agent_1"
    assert got["status"] == "completed"
    assert got["input"] == {"q": "hello"}
    assert got["output"] == {"a": "world"}

    history, total = await store.list_agent_history("agent_1", limit=10, offset=0)
    assert total == 1
    assert len(history) == 1
    assert history[0]["id"] == "exec_1"


@pytest.mark.asyncio
async def test_execution_store_skill_roundtrip(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    now = time.time()
    record = {
        "id": "sexec_1",
        "skill_id": "skill_1",
        "status": "failed",
        "input": {"x": 1},
        "output": None,
        "error": "boom",
        "start_time": now,
        "end_time": now + 0.2,
        "duration_ms": 200,
        "user_id": "system",
    }

    await store.upsert_skill_execution(record)

    got = await store.get_skill_execution("sexec_1")
    assert got is not None
    assert got["id"] == "sexec_1"
    assert got["skill_id"] == "skill_1"
    assert got["status"] == "failed"
    assert got["input"] == {"x": 1}
    assert got["error"] == "boom"

    executions, total = await store.list_skill_executions("skill_1", limit=10, offset=0)
    assert total == 1
    assert executions[0]["id"] == "sexec_1"

