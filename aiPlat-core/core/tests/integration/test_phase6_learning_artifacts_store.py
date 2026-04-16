import time

import pytest


@pytest.mark.asyncio
async def test_phase6_learning_artifact_roundtrip(tmp_path):
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    now = time.time()
    record = {
        "artifact_id": "art-1",
        "kind": "evaluation_report",
        "target_type": "agent",
        "target_id": "a1",
        "version": "v1",
        "status": "draft",
        "trace_id": "t1",
        "run_id": "r1",
        "payload": {"score": 0.9},
        "metadata": {"note": "test"},
        "created_at": now,
    }

    await store.upsert_learning_artifact(record)
    got = await store.get_learning_artifact("art-1")
    assert got is not None
    assert got["artifact_id"] == "art-1"
    assert got["payload"]["score"] == 0.9
    assert got["metadata"]["note"] == "test"

    lst = await store.list_learning_artifacts(target_type="agent", target_id="a1", limit=10, offset=0)
    assert lst["total"] >= 1
    assert any(i["artifact_id"] == "art-1" for i in lst["items"])

