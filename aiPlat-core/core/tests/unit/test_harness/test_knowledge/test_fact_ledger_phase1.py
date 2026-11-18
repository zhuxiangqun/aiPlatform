"""v4.3.1 Phase 1 G1：Raw 不可变、Fact 有 evidence、租户前置、跨租户隔离。"""
from __future__ import annotations

import pytest

from pathlib import Path


def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    load_object_type_bindings,
)


@pytest.fixture
async def ledger(tmp_path):
    """临时目录上的 FactLedger。"""
    db = tmp_path / "fact_ledger.sqlite3"
    raw = tmp_path / "raw"
    store = FactLedger(db_path=str(db), raw_dir=raw)
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_raw_immutable_source_has_sha256(ledger: FactLedger, tmp_path):
    """G1：Raw 不可变 — sha256 + snapshot 文件存在。"""
    content = b"pilot install order note"
    src = await ledger.register_source(
        tenant_id="tenant-a",
        collection_id="lock-kb",
        kind="file",
        uri="file://orders/note-1.txt",
        content=content,
        connector="phase1_test",
        domain_id="pilot-domain",
    )
    assert src["immutable"] is True
    assert len(src["sha256"]) == 64
    assert (tmp_path / "raw" / "tenant-a" / f"{src['source_id']}.bin").is_file()
    got = await ledger.get_source(src["source_id"], tenant_id="tenant-a")
    assert got is not None
    assert got["sha256"] == src["sha256"]


@pytest.mark.asyncio
async def test_published_fact_requires_evidence(ledger: FactLedger):
    """G1：无 evidence 不得 published。"""
    with pytest.raises(FactLedgerError, match="evidence"):
        await ledger.put_fact(
            tenant_id="tenant-a",
            collection_id="lock-kb",
            subject="order-1",
            predicate="status",
            object="pending",
            evidence=[],
            source_policy="primary_2026",
            extractor_version="test-1.0",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
        )


@pytest.mark.asyncio
async def test_fact_with_evidence_and_query_tenant_filter(ledger: FactLedger):
    """G1：Fact 有 evidence；查询按 tenant 前置过滤。"""
    src = await ledger.register_source(
        tenant_id="tenant-a",
        collection_id="lock-kb",
        kind="file",
        uri="file://orders/note-2.txt",
        content=b"status: pending",
        connector="phase1_test",
    )
    evidence = [
        {
            "source_id": src["source_id"],
            "locator": "p.1",
            "quote": "status: pending",
            "fetched_at": src["fetched_at"],
        }
    ]
    fact = await ledger.put_fact(
        tenant_id="tenant-a",
        collection_id="lock-kb",
        subject="InstallOrder:order-1",
        predicate="status",
        object="pending",
        evidence=evidence,
        source_policy="primary_2026",
        extractor_version="test-1.0",
        review_status="published",
        confidence=0.91,
        allow_bootstrap_published=True,
        domain_id="pilot-domain",
    )
    assert fact["evidence"]

    # 同租户可见
    rows = await ledger.query_facts(tenant_id="tenant-a", domain_id="pilot-domain")
    assert any(r["fact_id"] == fact["fact_id"] for r in rows)

    # 跨租户不可见
    other = await ledger.query_facts(tenant_id="tenant-b", domain_id="pilot-domain")
    assert other == []
    assert await ledger.get_source(src["source_id"], tenant_id="tenant-b") is None


@pytest.mark.asyncio
async def test_query_requires_tenant_id(ledger: FactLedger):
    """禁止无租户查询。"""
    with pytest.raises(FactLedgerError, match="tenant_id"):
        await ledger.query_facts(tenant_id="")


@pytest.mark.asyncio
async def test_gateway_abstains_without_citations(ledger: FactLedger):
    """无证据事实时网关 abstain。"""
    resp = await ledger.query_facts_gateway(
        tenant_id="tenant-a",
        query="anything",
        require_citations=True,
    )
    assert resp["abstained"] is True
    assert resp["citations"] == []


def test_load_object_type_bindings_from_seed():
    """试点 ObjectType 绑定经 JSON 种子加载（harness 不硬编码域名）。"""
    seed = (
        Path(__file__).resolve().parents[5]
        / "workspace_seeds"
        / "ontologies"
        / "lock-service-object-types.json"
    )
    # parents: test file → test_knowledge → test_harness → unit → tests → core → aiPlat-core
    if not seed.is_file():
        seed = (_repo_root() / "aiPlat-core/workspace_seeds/ontologies/lock-service-object-types.json")
    types = load_object_type_bindings(seed)
    ids = {t["object_type_id"] for t in types}
    assert "InstallOrder" in ids
    assert "DeviceModel" in ids
