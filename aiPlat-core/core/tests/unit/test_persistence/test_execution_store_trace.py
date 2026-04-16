import time

import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_trace_span_roundtrip(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    now = time.time()
    await store.upsert_trace(
        {
            "trace_id": "t1",
            "name": "trace",
            "status": "running",
            "start_time": now,
            "attributes": {"k": "v"},
        }
    )
    await store.upsert_span(
        {
            "span_id": "s1",
            "trace_id": "t1",
            "parent_span_id": None,
            "name": "span",
            "status": "running",
            "start_time": now,
            "attributes": {"a": 1},
            "events": [{"name": "e1", "timestamp": now, "attributes": {"x": 1}}],
        }
    )

    trace = await store.get_trace("t1", include_spans=True)
    assert trace is not None
    assert trace["trace_id"] == "t1"
    assert trace["attributes"]["k"] == "v"
    assert len(trace["spans"]) == 1
    assert trace["spans"][0]["span_id"] == "s1"
    assert trace["spans"][0]["events"][0]["name"] == "e1"

    traces, total = await store.list_traces(limit=10, offset=0)
    assert total == 1
    assert traces[0]["trace_id"] == "t1"

