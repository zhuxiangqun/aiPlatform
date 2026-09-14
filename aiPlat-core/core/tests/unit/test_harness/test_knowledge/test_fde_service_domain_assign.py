"""Phase 5+ second vertical: service-domain assign via config seed (no harness fork)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex

CANONICAL = "customer_action:service-domain:assign_technician"
DOMAIN = "service-domain"


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    return home


def _seed_work_orders(count: int = 2) -> list:
    g = GraphIndex(DOMAIN)
    ids = []
    for i in range(1, count + 1):
        eid = f"WO-UT-{i:04d}"
        g.add_entity(eid, f"WorkOrder {i}", "工单", source_doc_id="t")
        g.add_entity_property(eid, "state", "待指派")
        ids.append(eid)
    g.save()
    GraphIndex._loaded_instances.clear()
    return ids


@pytest.mark.asyncio
async def test_service_domain_assign_registers_and_executes(aiplat_home):
    reg = AsyncActionRegistry(store=AsyncMock())
    register_all(reg)
    c = reg.get(CANONICAL)
    assert c is not None
    assert c.domain_id == DOMAIN
    assert "assign_work_order" in (c.handler or "")
    assert not (c.aliases or [])

    ids = _seed_work_orders(2)
    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_sd")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)

    r = await reg.execute(
        CANONICAL,
        (DOMAIN, ids[0]),
        {"assigned_technician": "tech-sd-1"},
        actor="fda-sd",
        role="agent",
        _bypass_approval=True,
    )
    assert r.get("status") == "executed", r
    store.insert_audit.assert_awaited()
    mapped = store.insert_audit.await_args.args[0]
    assert mapped["action_id"] == CANONICAL
    assert mapped["params"].get("action_namespace") == "customer_action"

    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load(DOMAIN)
    node = g._nodes.get(ids[0])
    assert node is not None
    assert (node.metadata or {}).get("state") == "已指派"
    assert (node.metadata or {}).get("assigned_technician") == "tech-sd-1"
