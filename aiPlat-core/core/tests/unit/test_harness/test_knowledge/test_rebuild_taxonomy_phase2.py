"""Batch D：重建条件三分类契约（N05 partial）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_projector import (
    REBUILD_MODE_EXACT,
    REBUILD_MODE_NON,
    REBUILD_MODE_SEMANTIC,
    RebuildTaxonomyError,
    classify_rebuild,
    project_facts_to_graph,
    validate_rebuild_receipt,
)
from core.harness.knowledge_pipeline.fact_ledger import FactLedger


def test_classify_default_exact():
    mode, reason = classify_rebuild()
    assert mode == REBUILD_MODE_EXACT
    assert reason


def test_classify_rejects_exact_when_not_capable():
    with pytest.raises(RebuildTaxonomyError, match="exact_forbidden"):
        classify_rebuild(rebuild_mode=REBUILD_MODE_EXACT, exact_capable=False)


def test_classify_semantic_and_non():
    m1, r1 = classify_rebuild(rebuild_mode=REBUILD_MODE_SEMANTIC)
    assert m1 == REBUILD_MODE_SEMANTIC and r1
    m2, r2 = classify_rebuild(rebuild_mode=REBUILD_MODE_NON, exact_capable=False)
    assert m2 == REBUILD_MODE_NON and r2


def test_validate_receipt_requires_mode_and_reason():
    gate = validate_rebuild_receipt({"rebuild_mode": "", "rebuild_reason": ""})
    assert gate["ok"] is False
    assert "rebuild_mode_required" in gate["errors"]
    assert gate["certified"] is False
    assert gate["n05_full_conformance"] is False


def test_validate_rejects_exact_when_not_capable_flag():
    gate = validate_rebuild_receipt(
        {
            "rebuild_mode": REBUILD_MODE_EXACT,
            "rebuild_reason": "x",
            "projection_source": "fact_ledger",
            "exact_capable": False,
        }
    )
    assert gate["ok"] is False
    assert "exact_forbidden_when_not_exact_capable" in gate["errors"]


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_project_receipt_has_taxonomy(ledger: FactLedger, tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://1",
        content=b"x",
        connector="n05",
        domain_id="lock-service",
    )
    ev = [
        {
            "source_id": src["source_id"],
            "locator": "1",
            "quote": "x",
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
        source_policy="n05",
        extractor_version="t",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
        domain_id="lock-service",
    )
    out = await project_facts_to_graph(
        tenant_id="t1",
        domain_id="lock-service",
        ledger=ledger,
        clear_projected=True,
    )
    assert out["rebuild_mode"] == REBUILD_MODE_EXACT
    assert out.get("rebuild_reason")
    assert out["rebuild_gate"]["ok"] is True
    assert out["rebuild_gate"]["certified"] is False


@pytest.mark.asyncio
async def test_project_non_rebuildable_skips_write(
    ledger: FactLedger, tmp_path, monkeypatch
):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    out = await project_facts_to_graph(
        tenant_id="t1",
        domain_id="lock-service",
        ledger=ledger,
        rebuild_mode=REBUILD_MODE_NON,
        rebuild_reason="manual_view",
        exact_capable=False,
    )
    assert out["rebuild_mode"] == REBUILD_MODE_NON
    assert out["written"] is False
    assert out["created"] == []
    assert out["rebuild_gate"]["ok"] is True
