"""N14 Raw↔Fact↔Index 对账 deepen 单元测试。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline import raw_fact_index_reconcile as rfi


@pytest.mark.asyncio
async def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / production / cutover 恒 false。"""
    suite = await rfi.run_raw_fact_index_reconcile_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n14_full_conformance"] is False
    assert suite["production_reconcile_certified"] is False
    assert suite["process_cutover_authorized"] is False

    gate = rfi.evaluate_raw_fact_index_reconcile_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["issues"] == []


@pytest.mark.asyncio
async def test_index_incomplete_when_ids_none(tmp_path):
    """未提供 index_fact_ids → incomplete。"""
    from core.harness.knowledge_pipeline.fact_ledger import FactLedger

    lg = FactLedger(db_path=str(tmp_path / "fl.sqlite3"), raw_dir=tmp_path / "raw")
    await lg.initialize()
    out = await rfi.reconcile_raw_fact_index(
        tenant_id="t",
        index_fact_ids=None,
        ledger=lg,
    )
    assert out["index_incomplete"] is True
    assert out["ok"] is False
    assert out["production_reconcile_certified"] is False


@pytest.mark.asyncio
async def test_detects_index_orphan(tmp_path):
    """Index 幽灵 fact_id 上报。"""
    from core.harness.knowledge_pipeline.fact_ledger import FactLedger

    lg = FactLedger(db_path=str(tmp_path / "fl.sqlite3"), raw_dir=tmp_path / "raw")
    await lg.initialize()
    out = await rfi.reconcile_raw_fact_index(
        tenant_id="t",
        index_fact_ids=["ghost"],
        ledger=lg,
    )
    assert "ghost" in out["index_orphans"]


def test_gate_rejects_production_certified_flag():
    """禁止自签 production_reconcile_certified。"""
    gate = rfi.evaluate_raw_fact_index_reconcile_gate(
        {
            "ok": True,
            "passed": 6,
            "total": 6,
            "cases": [{"id": x, "ok": True} for x in rfi._SUITE_CASES],
            "production_reconcile_certified": True,
        }
    )
    assert gate["ok"] is False
    assert "honesty_production_reconcile_certified_forbidden" in gate["issues"]
