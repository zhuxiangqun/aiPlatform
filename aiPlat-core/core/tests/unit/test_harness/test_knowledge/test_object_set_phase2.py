"""W6 ObjectSet：租户前置 + L1 permissions + 只读。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.object_set import query_object_set


@pytest.fixture()
async def ledger(tmp_path):
    fl = FactLedger(db_path=str(tmp_path / "facts.db"), raw_dir=tmp_path / "raw")
    await fl.initialize()
    src = await fl.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="text",
        uri="mem://order1",
        content=b"order",
        connector="object_set_test",
    )
    ev = [{"source_id": src["source_id"], "locator": "1", "quote": "o"}]
    await fl.put_fact(
        tenant_id="t1",
        collection_id="c1",
        domain_id="lock-service",
        subject="InstallOrder:O-1",
        predicate="status",
        object="open",
        evidence=ev,
        source_policy="primary",
        extractor_version="test-1.0",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
    )
    await fl.put_fact(
        tenant_id="t1",
        collection_id="c1",
        domain_id="lock-service",
        subject="InstallOrder:O-1",
        predicate="device_model",
        object="X1",
        evidence=ev,
        source_policy="primary",
        extractor_version="test-1.0",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
    )
    await fl.put_fact(
        tenant_id="t1",
        collection_id="c1",
        domain_id="lock-service",
        subject="InstallOrder:O-2",
        predicate="status",
        object="closed",
        evidence=ev,
        source_policy="primary",
        extractor_version="test-1.0",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
    )
    src2 = await fl.register_source(
        tenant_id="t2",
        collection_id="c1",
        kind="text",
        uri="mem://other",
        content=b"x",
        connector="object_set_test",
    )
    await fl.put_fact(
        tenant_id="t2",
        collection_id="c1",
        domain_id="lock-service",
        subject="InstallOrder:O-9",
        predicate="status",
        object="open",
        evidence=[{"source_id": src2["source_id"], "locator": "1", "quote": "x"}],
        source_policy="primary",
        extractor_version="test-1.0",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
    )
    return fl


@pytest.mark.asyncio
async def test_policy_denied_without_kb_read(ledger):
    out = await query_object_set(
        {"object_type": "InstallOrder"},
        tenant_id="t1",
        permissions=["kb:write"],
        ledger=ledger,
    )
    assert out["status"] == "policy_denied"


@pytest.mark.asyncio
async def test_tenant_isolation(ledger):
    out = await query_object_set(
        {"object_type": "InstallOrder", "filter": {"status": "open"}},
        tenant_id="t1",
        permissions=["kb:read"],
        ledger=ledger,
    )
    assert out["status"] == "ok"
    assert out["total"] == 1
    assert out["items"][0]["order_id"] == "O-1"
    ids = {i.get("order_id") for i in out["items"]}
    assert "O-9" not in ids


@pytest.mark.asyncio
async def test_object_type_not_found(ledger):
    out = await query_object_set(
        {"object_type": "DoesNotExist"},
        tenant_id="t1",
        permissions=["kb:read"],
        ledger=ledger,
    )
    assert out["status"] == "not_found"


@pytest.mark.asyncio
async def test_tenant_id_required(ledger):
    out = await query_object_set(
        {"object_type": "InstallOrder"},
        tenant_id="",
        permissions=["kb:read"],
        ledger=ledger,
    )
    assert out["status"] == "error"
    assert out["reason"] == "tenant_id_required"


@pytest.mark.asyncio
async def test_query_does_not_write(ledger):
    before = await ledger.query_facts(tenant_id="t1", domain_id="lock-service", limit=100)
    out = await query_object_set(
        {"object_type": "InstallOrder", "limit": 10},
        tenant_id="t1",
        permissions=["*"],
        ledger=ledger,
    )
    assert out["status"] == "ok"
    after = await ledger.query_facts(tenant_id="t1", domain_id="lock-service", limit=100)
    assert len(before) == len(after)
