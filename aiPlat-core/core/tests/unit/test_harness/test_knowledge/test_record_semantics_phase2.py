"""N17 记录级语义校验 deepen 单元测试。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline import record_semantics as sem


@pytest.mark.asyncio
async def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / n17_full 恒 false。"""
    suite = await sem.run_record_semantics_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n17_full_conformance"] is False
    assert suite.get("runtime_authority") is True

    gate = sem.evaluate_record_semantics_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["n17_full_conformance"] is False
    assert gate["issues"] == []


def test_validate_record_rejects_published_without_evidence():
    """published 无 evidence 必须失败。"""
    r = sem.validate_record(
        "fact",
        {"evidence": [], "review_status": "published", "status": "active"},
    )
    assert r["ok"] is False
    assert "evidence is empty" in r["errors"]
    assert r["certified"] is False


def test_validate_transition_blocks_skip_review():
    """draft→published 跳过 review 必须拒绝。"""
    r = sem.validate_transition("fact_review", "draft", "published")
    assert r["ok"] is False
    ok = sem.validate_transition("fact_review", "draft", "reviewed")
    assert ok["ok"] is True


@pytest.mark.asyncio
async def test_scan_ledger_reports_clean_published_fact(tmp_path):
    """合法 published Fact 扫描 clean。"""
    from core.harness.knowledge_pipeline.fact_ledger import FactLedger

    lg = FactLedger(
        db_path=str(tmp_path / "fl.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await lg.initialize()
    tenant = "n17-scan-t"
    src = await lg.register_source(
        tenant_id=tenant,
        collection_id="c",
        kind="file",
        uri="file://n17/x",
        content=b"x",
        connector="n17",
        domain_id="d",
    )
    await lg.put_fact(
        tenant_id=tenant,
        collection_id="c",
        subject="Order:1",
        predicate="status",
        object="open",
        evidence=[
            {
                "source_id": src["source_id"],
                "locator": "1",
                "quote": "ok",
                "fetched_at": src["fetched_at"],
            }
        ],
        source_policy="n17",
        extractor_version="n17",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
        domain_id="d",
    )
    scan = await sem.scan_ledger_facts(tenant_id=tenant, domain_id="d", ledger=lg)
    assert scan["scanned"] == 1
    assert scan["clean"] is True
    assert scan["runtime_authority"] is True
    assert scan["certified"] is False
