"""E2：N06 Gateway 查询契约加深（附录 F.1；certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    evaluate_gateway_contract_gate,
    validate_gateway_response,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_abstain_has_f1_shape(ledger: FactLedger):
    resp = await ledger.query_facts_gateway(
        tenant_id="t1", query="none", require_citations=True
    )
    assert resp["abstained"] is True
    assert resp["answer"] == ""
    assert resp["citations"] == []
    assert "confidence_factors" in resp
    assert resp["gateway_contract_ok"] is True
    gate = validate_gateway_response(resp)
    assert gate["ok"] is True
    assert gate["certified"] is False


@pytest.mark.asyncio
async def test_hit_with_citations_contract(ledger: FactLedger):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n06/a.txt",
        content=b"status: open",
        connector="n06",
    )
    ev = [
        {
            "source_id": src["source_id"],
            "locator": "1",
            "quote": "open",
            "fetched_at": src["fetched_at"],
        }
    ]
    await ledger.put_fact(
        tenant_id="t1",
        collection_id="c1",
        subject="InstallOrder:o1",
        predicate="status",
        object="open",
        evidence=ev,
        source_policy="n06",
        extractor_version="t",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
        domain_id="lock-service",
    )
    resp = await ledger.query_facts_gateway(
        tenant_id="t1", query="InstallOrder", require_citations=True
    )
    assert resp["abstained"] is False
    assert resp["citations"]
    assert resp["answer"]
    assert resp["confidence_factors"]["evidence_coverage"] == 1.0
    assert validate_gateway_response(resp)["ok"] is True


@pytest.mark.asyncio
async def test_cross_tenant_gateway_no_leak(ledger: FactLedger):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n06/b.txt",
        content=b"secret",
        connector="n06",
    )
    ev = [
        {
            "source_id": src["source_id"],
            "locator": "1",
            "quote": "secret",
            "fetched_at": src["fetched_at"],
        }
    ]
    await ledger.put_fact(
        tenant_id="t1",
        collection_id="c1",
        subject="InstallOrder:secret",
        predicate="note",
        object="secret",
        evidence=ev,
        source_policy="n06",
        extractor_version="t",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
    )
    other = await ledger.query_facts_gateway(
        tenant_id="t2", query="secret", require_citations=True
    )
    assert other["facts"] == []
    assert other["abstained"] is True
    assert other["citations"] == []


def test_validate_rejects_missing_and_honesty():
    bad = validate_gateway_response({"answer": "x", "abstained": False})
    assert bad["ok"] is False
    assert any(e.startswith("missing:") for e in bad["errors"])
    assert bad["n06_full_conformance"] is False

    shape = {
        "answer": "",
        "citations": [],
        "route_plan": ["fact"],
        "route_reason": "x",
        "confidence": "low",
        "confidence_factors": {
            "evidence_coverage": 0,
            "source_authority": "low",
            "conflict": False,
            "coverage": 0,
            "freshness": "unknown",
        },
        "partial": False,
        "degraded": False,
        "abstained": True,
        "conflicts": [],
        "certified": True,
    }
    honest = validate_gateway_response(shape)
    assert honest["ok"] is False
    assert "honesty_certified_flag_forbidden" in honest["errors"]


def test_gate_honesty():
    ok_resp = {
        "answer": "",
        "citations": [],
        "route_plan": ["fact"],
        "route_reason": "x",
        "confidence": "low",
        "confidence_factors": {
            "evidence_coverage": 0,
            "source_authority": "low",
            "conflict": False,
            "coverage": 0,
            "freshness": "unknown",
        },
        "partial": False,
        "degraded": False,
        "abstained": True,
        "conflicts": [],
    }
    gate = evaluate_gateway_contract_gate([ok_resp])
    assert gate["ok"] is True
    assert gate["certified"] is False
    empty = evaluate_gateway_contract_gate([])
    assert empty["ok"] is False
    assert empty["certified"] is False
