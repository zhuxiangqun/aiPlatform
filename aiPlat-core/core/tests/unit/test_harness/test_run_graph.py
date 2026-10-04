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
async def test_mirror_does_not_overwrite_step_container(tmp_store):
    """routing_* must not replace step_* container name/kind when span_id collides."""
    from core.harness.observation import run_graph as rg

    run_id = "run_test_rg_step_protect"
    await rg.open_node(
        run_id,
        "step:architect_agent:1",
        kind="step",
        name="step_1",
        parent_id="agent:architect_agent:start",
        label="step_1",
        role="container",
        audit=False,
    )
    await rg.mirror_syscall_to_graph({
        "id": "evt_routing",
        "run_id": run_id,
        "span_id": "step:architect_agent:1",  # buggy emit reused step id
        "parent_span_id": "step:architect_agent:1",
        "kind": "routing",
        "name": "routing_strict_eval",
        "status": "eval",
        "start_time": 2.0,
        "end_time": 2.0,
        "duration_ms": 0,
        "args": {"selected_kind": "skill", "selected_name": "architecture_design"},
    })
    g = await rg.get_graph(run_id)
    by_id = {n["node_id"]: n for n in g["nodes"]}
    step = by_id["step:architect_agent:1"]
    assert step["name"] == "step_1"
    assert step["kind"] == "step"
    assert step["role"] == "container"
    # Work node must exist under a distinct id
    work_ids = [nid for nid in by_id if nid != "step:architect_agent:1"]
    assert work_ids, "expected redirected routing work node"
    work = by_id[work_ids[0]]
    assert work["name"] == "routing_strict_eval"
    assert work["parent_id"] == "step:architect_agent:1"


@pytest.mark.asyncio
async def test_mirror_skill_route_before_skill_keeps_skill_card(tmp_store):
    """skill_route(selected→ok) must not block later skill/running on same span."""
    from core.harness.observation import run_graph as rg

    run_id = "run_test_rg_route_then_skill"
    skill_span = "uuid-skill-autoreview-2"
    await rg.open_node(
        run_id,
        "step:frontend_engineer:1",
        kind="step",
        name="step_1",
        parent_id="agent:frontend_engineer:start",
        role="container",
        audit=False,
    )
    # Route first (production order in sys_skill_call)
    await rg.mirror_syscall_to_graph({
        "id": "evt_route_first",
        "run_id": run_id,
        "span_id": skill_span,
        "parent_span_id": "step:frontend_engineer:1",
        "kind": "routing",
        "name": "skill_route",
        "status": "selected",
        "start_time": 1.0,
        "end_time": 1.0,
        "duration_ms": 0.2,
        "args": {"skill": "autoreview"},
    })
    await rg.mirror_syscall_to_graph({
        "id": "evt_skill_run",
        "run_id": run_id,
        "span_id": skill_span,
        "parent_span_id": "step:frontend_engineer:1",
        "kind": "skill",
        "name": "autoreview",
        "status": "running",
        "start_time": 1.01,
    })
    g = await rg.get_graph(run_id)
    by_id = {n["node_id"]: n for n in g["nodes"]}
    assert skill_span in by_id
    skill = by_id[skill_span]
    assert skill["kind"] == "skill"
    assert skill["name"] == "autoreview"
    assert skill["status"] == "running"
    route_ids = [nid for nid, n in by_id.items() if n.get("name") == "skill_route"]
    assert route_ids and skill_span not in route_ids
    assert all(str(nid).startswith("routing:") for nid in route_ids)


@pytest.mark.asyncio
async def test_upsert_sql_blocks_routing_clobber_of_skill(tmp_store):
    """DB upsert must keep skill kind/name when a routing row hits the same node_id."""
    run_id = "run_test_rg_sql_skill_guard"
    nid = "uuid-shared-span"
    await tmp_store.upsert_run_graph_node({
        "run_id": run_id,
        "node_id": nid,
        "parent_id": "step:frontend_engineer:1",
        "kind": "skill",
        "name": "autoreview",
        "label": "autoreview",
        "role": "work",
        "status": "ok",
        "start_time": 1.0,
        "end_time": 2.0,
        "duration_ms": 1000,
        "args": {},
        "result": {},
        "sort_key": 1.0,
        "updated_at": 2.0,
    })
    await tmp_store.upsert_run_graph_node({
        "run_id": run_id,
        "node_id": nid,
        "parent_id": "step:frontend_engineer:1",
        "kind": "routing",
        "name": "skill_route",
        "label": "skill_route",
        "role": "work",
        "status": "ok",
        "start_time": 1.0,
        "end_time": 1.1,
        "duration_ms": 0.2,
        "args": {"skill": "autoreview"},
        "result": {},
        "sort_key": 1.1,
        "updated_at": 1.1,
    })
    got = await tmp_store.get_run_graph_node(run_id, nid)
    assert got["kind"] == "skill"
    assert got["name"] == "autoreview"


@pytest.mark.asyncio
async def test_mirror_remaps_invented_run_skill_parent_to_skill_node(tmp_store):
    """`{run}:skill:NAME` parent must remap to the real skill UUID/stable node."""
    from core.harness.observation import run_graph as rg

    run_id = "run-test-rg-remap"
    await rg.open_node(
        run_id,
        "step:frontend_engineer:1",
        kind="step",
        name="step_1",
        parent_id="agent:frontend_engineer:start",
        role="container",
        audit=False,
    )
    await rg.open_node(
        run_id,
        "89f2641b-skill-uuid",
        kind="skill",
        name="code_generation",
        parent_id="step:frontend_engineer:1",
        role="work",
        audit=False,
    )
    await rg.mirror_syscall_to_graph({
        "id": "evt_gen2",
        "run_id": run_id,
        "span_id": "uuid-llm-generate-2",
        "parent_span_id": f"{run_id}:skill:code_generation",
        "kind": "llm",
        "name": "generate",
        "status": "ok",
        "start_time": 4.0,
        "end_time": 5.0,
        "duration_ms": 1000,
    })
    g = await rg.get_graph(run_id)
    by_id = {n["node_id"]: n for n in g["nodes"]}
    gen = by_id["uuid-llm-generate-2"]
    assert gen["parent_id"] == "89f2641b-skill-uuid"
    roots = {str(r.get("node_id") or r.get("id")) for r in g["roots"]}
    assert "uuid-llm-generate-2" not in roots


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
