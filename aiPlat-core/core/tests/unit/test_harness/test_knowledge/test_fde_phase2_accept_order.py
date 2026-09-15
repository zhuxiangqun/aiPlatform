"""Phase 2: D3 canonical accept_order execute path + audit embed (alias deprecated)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex

CANONICAL = "customer_action:lock-service:accept_order"


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    return home


def _seed_orders(domain: str, prefix: str, count: int) -> list:
    g = GraphIndex(domain)
    ids = []
    for i in range(1, count + 1):
        eid = f"{prefix}-{i:04d}"
        g.add_entity(eid, f"Order {i}", "安装工单", source_doc_id="t")
        g.add_entity_property(eid, "state", "pending")
        ids.append(eid)
    g.save()
    GraphIndex._loaded_instances.clear()
    return ids


@pytest.mark.asyncio
async def test_d3_legacy_alias_removed(aiplat_home):
    """D3 close-out: accept_order alias no longer registered."""
    reg = AsyncActionRegistry(store=AsyncMock())
    register_all(reg)
    assert reg.get("accept_order") is None
    c = reg.get(CANONICAL)
    assert c is not None
    assert c.action_id == CANONICAL
    assert not (c.aliases or [])


@pytest.mark.asyncio
async def test_accept_order_l1_rejects_non_pending(aiplat_home):
    """Ontology runtime L1: wrong state must be blocked before handler (LS-A1)."""
    domain = "lock-service"
    g = GraphIndex(domain)
    eid = "IO-BAD-0001"
    g.add_entity(eid, "Order bad", "安装工单", source_doc_id="t")
    g.add_entity_property(eid, "state", "completed")
    g.save()
    GraphIndex._loaded_instances.clear()

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_x")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)

    # Direct L1 check
    c = reg.check_entity_constraints(
        CANONICAL, domain, "安装工单", "completed", role="agent"
    )
    assert c.get("valid") is False
    assert c.get("constraint_type") == "state"

    r = await reg.execute(
        CANONICAL,
        (domain, eid),
        {"assigned_technician": "tech-9"},
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r.get("status") == "blocked", r
    assert r.get("constraint_type") == "state"
    # L3: blocked attempts still leave an audit failure record (not silent)
    store.insert_audit.assert_awaited()
    aud = store.insert_audit.await_args.args[0]
    assert aud.get("result_status") == "failure"
    assert aud.get("constraint_type") == "state"


@pytest.mark.asyncio
async def test_accept_order_execute_canonical(aiplat_home):
    domain = "lock-service"
    ids = _seed_orders(domain, "IO-UT", 2)

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_1")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)

    r1 = await reg.execute(
        CANONICAL,
        (domain, ids[0]),
        {"assigned_technician": "tech-9", "scheduled_at": "2026-09-15T09:00:00+08:00"},
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r1.get("status") == "executed", r1
    store.insert_audit.assert_awaited()
    mapped = store.insert_audit.await_args.args[0]
    assert mapped["params"]["schema"] == "audit.v1"
    assert mapped["params"]["action_namespace"] == "customer_action"
    assert mapped["action_id"] == CANONICAL

    r2 = await reg.execute(
        CANONICAL,
        (domain, ids[1]),
        {"technician_id": "tech-2"},
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r2.get("status") == "executed", r2


@pytest.mark.asyncio
async def test_bench_sample_20_zero_fail(aiplat_home):
    """Lightweight D4 sample (20) — full 200 via scripts/bench_accept_order_p95.py."""
    ids = _seed_orders("lock-service", "IO-S20", 20)
    store = AsyncMock()
    store.insert_audit = AsyncMock(side_effect=lambda rec: "aud")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    fails = 0
    for eid in ids:
        r = await reg.execute(
            "customer_action:lock-service:accept_order",
            ("lock-service", eid),
            {"assigned_technician": "t1"},
            actor="bench",
            role="agent",
            _bypass_approval=True,
        )
        if r.get("status") != "executed":
            fails += 1
    assert fails == 0
    assert store.insert_audit.await_count == 20
