"""W8 ObjectSet ABox ACL：实例拒绝 + 字段脱敏 + 跨租户负向。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.object_set import query_object_set
from core.policy.graph_abox_acl import set_entity_acl, set_field_acl


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    return home


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
        connector="object_set_acl_test",
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
    )
    await fl.put_fact(
        tenant_id="t1",
        collection_id="c1",
        domain_id="lock-service",
        subject="InstallOrder:O-1",
        predicate="device_model",
        object="secret-model",
        evidence=ev,
        source_policy="primary",
        extractor_version="test-1.0",
        review_status="published",
        confidence=0.9,
    )
    await fl.put_fact(
        tenant_id="t1",
        collection_id="c1",
        domain_id="lock-service",
        subject="InstallOrder:O-2",
        predicate="status",
        object="open",
        evidence=ev,
        source_policy="primary",
        extractor_version="test-1.0",
        review_status="published",
        confidence=0.9,
    )
    src2 = await fl.register_source(
        tenant_id="t2",
        collection_id="c1",
        kind="text",
        uri="mem://other",
        content=b"x",
        connector="object_set_acl_test",
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
    )
    return fl


@pytest.mark.asyncio
async def test_entity_acl_filters_denied_instance(ledger, aiplat_home):
    set_entity_acl(
        "lock-service",
        "O-2",
        deny_roles={"viewer": ["read"]},
        allow_roles={"admin": ["*"]},
    )
    out = await query_object_set(
        {"object_type": "InstallOrder", "filter": {"status": "open"}, "aggregate": [{"type": "count"}]},
        tenant_id="t1",
        permissions=["kb:read"],
        role="viewer",
        ledger=ledger,
    )
    assert out["status"] == "ok"
    ids = {i.get("order_id") for i in out["items"]}
    assert ids == {"O-1"}
    assert "O-2" not in ids
    # 为什么：聚合不得泄漏被拒绝实例
    assert out["aggregates"] == [{"count": 1}]


@pytest.mark.asyncio
async def test_field_acl_redacts_for_viewer(ledger, aiplat_home):
    set_field_acl(
        "lock-service",
        "O-1",
        "device_model",
        visibility="role:admin",
        redaction="replace",
        replace_with="[REDACTED]",
    )
    viewer = await query_object_set(
        {"object_type": "InstallOrder", "filter": {"order_id": "O-1"}},
        tenant_id="t1",
        permissions=["kb:read"],
        role="viewer",
        ledger=ledger,
    )
    assert viewer["status"] == "ok"
    assert viewer["items"][0]["device_model"] == "[REDACTED]"

    admin = await query_object_set(
        {"object_type": "InstallOrder", "filter": {"order_id": "O-1"}},
        tenant_id="t1",
        permissions=["kb:read"],
        role="admin",
        ledger=ledger,
    )
    assert admin["items"][0]["device_model"] == "secret-model"


@pytest.mark.asyncio
async def test_cross_tenant_zero_leak(ledger, aiplat_home):
    out = await query_object_set(
        {"object_type": "InstallOrder"},
        tenant_id="t1",
        permissions=["kb:read"],
        role="admin",
        ledger=ledger,
    )
    assert out["status"] == "ok"
    ids = {i.get("order_id") for i in out["items"]}
    assert "O-9" not in ids
