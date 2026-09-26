"""Unit tests for RunGraph open/close/get_graph lifecycle."""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture()
def tmp_store(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", path)
    # Reset singleton
    import core.services.execution_store as es_mod
    es_mod._execution_store = None
    from core.services.execution_store import get_execution_store
    store = get_execution_store(path)
    yield store
    es_mod._execution_store = None
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_open_close_get_graph(tmp_store):
    from core.harness.observation import run_graph as rg

    run_id = "run_test_rg_1"
    await rg.open_node(
        run_id,
        "skill:demo",
        kind="skill",
        name="demo",
        label="demo",
        role="work",
        audit=False,
    )
    g1 = await rg.get_graph(run_id)
    assert g1["has_graph"] is True
    assert g1["status"] == "running"
    assert len(g1["nodes"]) == 1
    assert len(g1["roots"]) == 1
    root = g1["roots"][0]
    assert root["name"] == "demo"
    assert root["status"] == "running"

    await rg.close_node(run_id, "skill:demo", status="ok", result={"ok": True}, audit=False)
    done = await rg.mark_run_done(run_id, status="completed")
    assert done["status"] == "completed"

    g2 = await rg.get_graph(run_id)
    assert g2["status"] == "completed"
    by_id = {n["node_id"]: n for n in g2["nodes"]}
    assert by_id["skill:demo"]["status"] == "ok"


@pytest.mark.asyncio
async def test_mirror_coalesces_into_stable_skill_node(tmp_store):
    from core.harness.observation import run_graph as rg

    run_id = "run_test_rg_coalesce"
    await rg.open_node(run_id, "skill:demo", kind="skill", name="demo", label="demo", role="work", audit=False)
    await rg.mirror_syscall_to_graph({
        "id": "evt1",
        "run_id": run_id,
        "span_id": "uuid-span-should-fold",
        "parent_span_id": "skill:demo",
        "kind": "skill",
        "name": "demo",
        "status": "success",
        "start_time": 1.0,
        "end_time": 1.2,
        "duration_ms": 200,
        "result": {"output": {"path": "/tmp/x.pptx"}},
    })
    g = await rg.get_graph(run_id)
    assert len(g["nodes"]) == 1
    assert g["nodes"][0]["node_id"] == "skill:demo"
    assert g["nodes"][0]["status"] == "ok"


@pytest.mark.asyncio
async def test_mark_run_done_closes_running(tmp_store):
    from core.harness.observation import run_graph as rg

    run_id = "run_test_rg_2"
    await rg.open_node(run_id, "n1", kind="skill", name="skill_start", role="container", audit=False)
    await rg.open_node(run_id, "n2", kind="skill", name="work", parent_id="n1", role="work", audit=False)
    result = await rg.mark_run_done(run_id, status="failed")
    assert "n1" in result["closed"] or "n2" in result["closed"]
    g = await rg.get_graph(run_id)
    assert g["status"] == "failed"
    for n in g["nodes"]:
        assert n["status"] != "running"
